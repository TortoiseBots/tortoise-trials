"""Bench round 1116: potion carryover scoring and the cross-rep item-cooldown gap.

Fail-first: each case failed on the base commit (old code) and passes with the fix.

- PotionCarryoverTest scores a fixture shaped like the rc1116 run's events
  (first potions -0.29, 19.9, 38.5, 59.1, 76.8, -0.32 on 220 s rep spacing):
  the four carried-over reps are INCONCLUSIVE with reason
  "item cooldown from rep N-1", the two clean reps score normally. One case puts
  the rep's first cast INSIDE the old cooldown span (impossible, or a proc row)
  and the real first potion just past expiry: the carried-over rep must still be
  INCONCLUSIVE, never a late-cast miss on the second potion.
- PotionMinRepGapTest pins the runner side: the trial carries
  situation.min_rep_gap_s (validate accepts it) and wait_rep_gap sleeps until
  130 s after the previous rep's last potion (no potion yet: no wait; rep2 and
  rep10: numeric rep order, the newest potion wins).
"""

import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from trl import scenario as scenario_mod  # noqa: E402
from trl import score as score_mod  # noqa: E402
from trl.live import run as run_mod  # noqa: E402


PLAYER = "0x0000000000000001"
BOT = "0x0000000000000002"
MOB = "0xf13000000000abcd"
TID = "priest-holy-low-mana-potion"


def load_trial():
    return scenario_mod.load_trial(os.path.join(ROOT, "trials", "edge", TID + ".json"))


def wall(base, offset):
    import datetime
    return datetime.datetime.fromtimestamp(base + offset,
                                           datetime.timezone.utc).isoformat(timespec="milliseconds")


def event(t, spell="Restore Mana"):
    return {"t": float(t), "wall": None, "kind": "cast", "src": "bot", "src_guid": BOT,
            "dst": "bot", "dst_guid": BOT, "spell": spell, "spell_id": 11903,
            "dst_hp_pct": 60, "origin": "ta"}


def write_rep(trial_dir, name, base, potions):
    rep = os.path.join(trial_dir, name)
    os.makedirs(rep)
    setup = {"ok": True, "guids": {"player": PLAYER, "bot": BOT, "mobs": [MOB]}, "config": {}}
    with open(os.path.join(rep, "setup.json"), "w") as f:
        json.dump(setup, f)
    marks = [{"kind": "fight_start", "wall": wall(base, 0)},
             {"kind": "fight_end", "wall": wall(base, 200), "ended": "duration"}]
    rows = [event(t) for t in potions]
    for fname, data in (("marks.jsonl", marks), ("events.jsonl", rows), ("samples.jsonl", [])):
        with open(os.path.join(rep, fname), "w") as f:
            for row in data:
                f.write(json.dumps(row) + "\n")
    return rep


def score_reps(potions_per_rep, spacing=None):
    # the rc1116 wall spacings (fight_start to fight_start): uniform 220 s puts a
    # carried first potion back inside the old cooldown span by fractions of a
    # second, while the run's real 219.6-222.4 s spacings land it just past expiry.
    gaps = [220.0, 221.5, 219.587, 222.392, 220.598]
    with tempfile.TemporaryDirectory() as tmp:
        tdir = os.path.join(tmp, "run", TID)
        base = 1_800_000_000.0
        for i, pots in enumerate(potions_per_rep):
            if i:
                base += spacing if spacing else gaps[min(i - 1, len(gaps) - 1)]
            write_rep(tdir, "rep%d" % (i + 1), base, pots)
        trial = load_trial()
        return score_mod.score_trial(tdir, trial)["verdicts"][0]


class PotionCarryoverTest(unittest.TestCase):
    def test_recorded_values_rescore_to_four_inconclusive_two_scored(self):
        pots = [[-0.29, 119.77], [19.89, 139.93], [38.51, 158.59],
                [59.08, 179.13], [76.78], [-0.32, 119.81]]
        got = score_reps(pots)
        by_rep = {d["rep"]: d for d in got["detail"]}
        self.assertEqual(by_rep["rep1"]["verdict"], "PASS")
        self.assertEqual(by_rep["rep6"]["verdict"], "PASS")
        for rep in ("rep2", "rep3", "rep4", "rep5"):
            self.assertEqual(by_rep[rep]["verdict"], "INCONCLUSIVE", rep)
            self.assertEqual(by_rep[rep]["reason"], "item cooldown from rep N-1", rep)
            self.assertEqual(by_rep[rep]["k"], 0)
            self.assertEqual(by_rep[rep]["n"], 0)

    def test_a_first_potion_past_the_grace_scores_normally(self):
        # 150 s after the previous rep's last potion: the bot had a free window.
        got = score_reps([[10], [10]], spacing=260.0)
        rep2 = [d for d in got["detail"] if d["rep"] == "rep2"][0]
        self.assertEqual(rep2["verdict"], "PASS")

    def test_no_potion_in_a_partially_covered_window_is_still_a_miss(self):
        # a rep with NO potion still scores the +inf path (unchanged bench-1112 shape).
        got = score_reps([[10], []])
        rep2 = [d for d in got["detail"] if d["rep"] == "rep2"][0]
        self.assertEqual(rep2["verdict"], "FAIL")

    def test_a_first_hit_inside_the_old_cooldown_cannot_hide_the_carryover(self):
        # rep1's last potion is late (t 200 on a 220 s rep), so rep2's cooldown span is
        # [-20, 100]. rep2's first potion at t 5 sits INSIDE that span (impossible, or a
        # proc row) and was `ordered[0]` before the fix: the carryover branch was skipped
        # and the real first potion (t 100.5, 120.5 s after rep1's last) scored 100.5 -> FAIL.
        got = score_reps([[200], [5, 100.5]])
        rep2 = [d for d in got["detail"] if d["rep"] == "rep2"][0]
        self.assertEqual(rep2["verdict"], "INCONCLUSIVE", rep2)
        self.assertEqual(rep2["reason"], "item cooldown from rep N-1")


class PotionMinRepGapTest(unittest.TestCase):
    def test_the_trial_carries_a_documented_min_rep_gap(self):
        trial = load_trial()
        self.assertEqual(trial["situation"]["min_rep_gap_s"], 130)
        self.assertEqual(scenario_mod.validate(trial), [])
        bad = dict(trial)
        bad["situation"] = dict(trial["situation"], min_rep_gap_s=-5)
        self.assertTrue(any("min_rep_gap_s" in e for e in scenario_mod.validate(bad)))

    def _run(self, tmp):
        run = run_mod.Run.__new__(run_mod.Run)
        run.run_dir = tmp
        calls = []
        run.log = calls.append
        return run, calls

    def _waited(self, run, trial, gap):
        import time as _time
        slept = []
        real_sleep = _time.sleep
        _time.sleep = slept.append
        try:
            waited = run.wait_rep_gap(None, trial, gap)
        finally:
            _time.sleep = real_sleep
        self.assertEqual(len(slept), 1)
        return waited

    def test_wait_rep_gap_waits_for_the_item_cooldown(self):
        import datetime
        now = datetime.datetime.now(datetime.timezone.utc).timestamp()
        with tempfile.TemporaryDirectory() as tmp:
            trial = load_trial()
            tdir = os.path.join(tmp, TID)
            os.makedirs(tdir)
            # previous rep's last potion 100 s ago: a 130 s gap still owes 30 s.
            write_rep(tdir, "rep1", now - 100 - 119.0, [119.0])
            run, _calls = self._run(tmp)
            waited = self._waited(run, trial, 130.0)
            self.assertGreater(waited, 29.0)
            self.assertLess(waited, 31.0)

    def test_wait_rep_gap_reads_rep_dirs_numerically_and_keeps_the_newest_potion(self):
        # rep10's potion is 50 s old, rep2's is 300 s old: a string sort visits rep10
        # first and rep2's older wall overwrote it, so the 130 s gap owed 80 s and the
        # old code slept 0 s.
        import datetime
        now = datetime.datetime.now(datetime.timezone.utc).timestamp()
        with tempfile.TemporaryDirectory() as tmp:
            trial = load_trial()
            tdir = os.path.join(tmp, TID)
            os.makedirs(tdir)
            write_rep(tdir, "rep2", now - 300.0 - 100.0, [100.0])     # last potion 300 s ago
            write_rep(tdir, "rep10", now - 50.0 - 100.0, [100.0])     # last potion 50 s ago
            run, calls = self._run(tmp)
            waited = self._waited(run, trial, 130.0)
            self.assertGreater(waited, 79.0)
            self.assertLess(waited, 81.0)
            self.assertTrue(any("waiting" in line for line in calls))

    def test_no_potion_yet_means_no_wait(self):
        with tempfile.TemporaryDirectory() as tmp:
            trial = load_trial()
            os.makedirs(os.path.join(tmp, TID))
            run, _calls = self._run(tmp)
            self.assertEqual(run.wait_rep_gap(None, trial, 130.0), 0.0)


if __name__ == "__main__":
    unittest.main()
