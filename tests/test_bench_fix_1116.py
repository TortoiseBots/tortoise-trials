"""Bench round 1116: potion carryover scoring and the dispel setup order.

Fail-first: each case failed on the base commit (old code) and passes with the fix.

- PotionCarryoverTest scores a fixture shaped like the rc1116 run's events
  (first potions -0.29, 19.9, 38.5, 59.1, 76.8, -0.32 on 220 s rep spacing):
  the four carried-over reps are INCONCLUSIVE with reason
  "item cooldown from rep N-1", the two clean reps score normally.
- PotionMinRepGapTest pins the runner side: the trial carries
  situation.min_rep_gap_s (validate accepts it) and wait_rep_gap sleeps until
  130 s after the previous rep's last potion (no potion yet: no wait).
- DispelSetupOrderTest pins the setup side: check_player_auras sends the wanted
  aura and retries a missing one once (two `.aura 770` lines), and the debuff
  lands after the pull in Situation.run (debuff apply after engage/pull).
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
from trl.live import setup as setup_mod  # noqa: E402


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


class PotionMinRepGapTest(unittest.TestCase):
    def test_the_trial_carries_a_documented_min_rep_gap(self):
        trial = load_trial()
        self.assertEqual(trial["situation"]["min_rep_gap_s"], 130)
        self.assertEqual(scenario_mod.validate(trial), [])
        bad = dict(trial)
        bad["situation"] = dict(trial["situation"], min_rep_gap_s=-5)
        self.assertTrue(any("min_rep_gap_s" in e for e in scenario_mod.validate(bad)))

    def test_wait_rep_gap_waits_for_the_item_cooldown(self):
        import datetime
        now = datetime.datetime.now(datetime.timezone.utc).timestamp()
        with tempfile.TemporaryDirectory() as tmp:
            trial = load_trial()
            tdir = os.path.join(tmp, TID)
            os.makedirs(tdir)
            # previous rep's last potion 100 s ago: a 130 s gap still owes 30 s.
            write_rep(tdir, "rep1", now - 100 - 119.0, [119.0])
            run = run_mod.Run.__new__(run_mod.Run)
            run.run_dir = tmp
            calls = []

            class Log:
                def __call__(self, line):
                    calls.append(line)
            run.log = Log()
            import time as _time
            slept = []
            real_sleep = _time.sleep
            _time.sleep = slept.append
            try:
                waited = run.wait_rep_gap(None, trial, 130.0)
            finally:
                _time.sleep = real_sleep
            self.assertGreater(waited, 29.0)
            self.assertLess(waited, 31.0)
            self.assertEqual(len(slept), 1)

    def test_no_potion_yet_means_no_wait(self):
        with tempfile.TemporaryDirectory() as tmp:
            trial = load_trial()
            os.makedirs(os.path.join(tmp, TID))
            run = run_mod.Run.__new__(run_mod.Run)
            run.run_dir = tmp
            run.log = lambda line: None
            self.assertEqual(run.wait_rep_gap(None, trial, 130.0), 0.0)


class FakeAgent:
    """check_player_auras needs: status, unit (auras), and the guard's gm/target rpcs."""

    PLAYER = "0x0000000000000001"

    def __init__(self, auras=()):
        self.auras = list(auras)
        self.gm = []
        self.targets = []
        self.selection_gen = 0
        from threading import Lock
        self.action_lock = Lock()

    def status(self):
        # the guard reads the selection from status().target right after rpc target.
        return {"state": "in_world", "guid": self.PLAYER,
                "target": self.targets[-1] if self.targets else self.PLAYER}

    def own_row(self):
        return self.unit()

    def unit(self, guid=None, name=None):
        # the guard confirms the selection from the player's own unit row: the
        # server echoes the selected guid in its target field.
        return {"guid": self.PLAYER, "target": self.targets[-1] if self.targets else self.PLAYER,
                "auras": [{"spell_id": a} for a in self.auras]}
    def rpc(self, method, params=None, timeout=None):
        if method == "status":
            return dict(self.status())
        if method == "target":
            self.targets.append((params or {}).get("guid"))
            return {"guid": (params or {}).get("guid")}
        if method == "gm":
            text = (params or {}).get("text") or ""
            self.gm.append(text)
            if text.startswith(".aura"):
                # the first 770 send is lost on the wire (the rc1116 shape: the aura
                # never lands); the retry lands.
                self.aura_sends = getattr(self, "aura_sends", 0) + 1
                if not (text == ".aura 770" and self.aura_sends == 1):
                    try:
                        self.auras.append(int(text.split()[1]))
                    except (IndexError, ValueError):
                        pass
            return {}

class DispelSetupOrderTest(unittest.TestCase):
    def trial(self):
        return {"id": "t", "player": {"class": "warrior", "level": 40, "auras": [770],
                                      "talents": {"tree": "arms", "spells": []}}}

    def test_missing_aura_is_retried_once_then_proven(self):
        from trl.live import gm_guard
        from trl.live.ledger import Ledger
        with tempfile.TemporaryDirectory() as tmp:
            agent = FakeAgent(auras=[71])
            ctx = gm_guard.GmContext(player_guid=FakeAgent.PLAYER, aura_ids=frozenset({71, 770}))
            guard = gm_guard.GmGuard(agent, Ledger(os.path.join(tmp, "l.jsonl")), ctx)
            calls = []

            orig_send = guard.send

            def send(kind, target=None, *args):
                calls.append((kind, args[0] if args else None))
                return orig_send(kind, target, *args)

            guard.send = send
            row = setup_mod.check_player_auras(agent, self.trial(), guard, ctx)
            self.assertTrue(row["ok"], row)
            self.assertEqual(sorted(row["value"]), [71, 770])
            # one send per wanted aura, then the retry of the missing 770 only.
            self.assertEqual([c[1] for c in calls if c[0] == "aura"], [770, 770])

    def test_still_missing_after_the_retry_fails(self):
        from trl.live import gm_guard
        from trl.live.ledger import Ledger

        class DropAura(FakeAgent):
            def rpc(self, method, params=None, timeout=None):
                if method == "gm" and (params or {}).get("text", "").startswith(".aura 770"):
                    return {}
                return FakeAgent.rpc(self, method, params, timeout)

        with tempfile.TemporaryDirectory() as tmp:
            agent = DropAura(auras=[71])
            ctx = gm_guard.GmContext(player_guid=FakeAgent.PLAYER, aura_ids=frozenset({71, 770}))
            row = setup_mod.check_player_auras(
                agent, self.trial(), gm_guard.GmGuard(
                    agent, Ledger(os.path.join(tmp, "l.jsonl")), ctx), ctx)
            self.assertFalse(row["ok"])
            self.assertIn("missing [770]", row["evidence"])

    def test_debuff_lands_after_the_pull_not_before(self):
        import inspect
        src = inspect.getsource(setup_mod.check_player_auras)
        self.assertIn("retry", src)
        import trl.live.situations as sit
        run_src = inspect.getsource(sit.Situation.run)
        self.assertLess(run_src.index("self.pull()"), run_src.index("apply_debuff"))


if __name__ == "__main__":
    unittest.main()
