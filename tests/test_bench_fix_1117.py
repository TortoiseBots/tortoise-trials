"""Bench fix 1117: pull_wait early-combat stamp, fight_deadline, facing threat/attack.

Fail-first: each case failed on the base commit (no pull_wait/fight_deadline
methods, threat()/attack() never face, no early_fight on the card) and passes
with the fix. Round 1 adds: pull_wait retries a failed unit read; threat()
and attack() skip the trial's CC mark; the early stamp sets fight_seen; and the
run() wiring is a behaviour test, not source inspection. Round 2 adds: a read
that dies with the session/lease (abort_reason set) ends pull_wait and the
repeat at once — no retry, nothing sent after the wait — while a plain read
failure is still retried.
"""

import os
import sys
import tempfile
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

import test_live as tl  # noqa: E402
from trl.live import agent as agent_mod  # noqa: E402
from trl.live import situations  # noqa: E402

norm = agent_mod.norm_guid
LIVE = norm("0xF13000000000ABCD")
DEAD = norm("0xF13000000000ABCE")


class FaceAgent(tl.FakeAgent):
    """A FakeAgent whose `face` rpc succeeds (the real one answers {})."""

    def rpc(self, method, params=None, timeout=None):
        if method == "face":
            self.calls.append((method, params))
            return {}
        return tl.FakeAgent.rpc(self, method, params, timeout)


def make_trial(**over):
    base = {"id": "t", "player": {"level": 40, "class": "warrior", "stance": 71},
            "situation": {"kind": "tank_damage", "mobs": {"role": "melee", "count": 1}},
            "duration_s": 60}
    base.update(over)
    return base


def make_sit(agent, ledger_guids=(), marks=None):
    tmp = tempfile.mkdtemp()
    led = tl.new_ledger(tmp)
    for guid in ledger_guids:
        led.add({"kind": "summon", "guid": guid})
    sit = situations.Situation(agent, make_trial(), None, led,
                               marks if marks is not None else tl.FakeMarks(),
                               tl.StubCollector(),
                               situations.SitContext(player_guid=tl.PLAYER),
                               arenas=[], mobs={})
    sit.summoned = list(ledger_guids)
    return sit


class PullWaitTest(unittest.TestCase):
    def test_pull_wait_stamps_fight_start_on_early_combat(self):
        agent = FaceAgent()
        agent.units_queue = [[], [{"guid": LIVE, "in_combat": True, "dead": False}]]
        sit = make_sit(agent, [LIVE])
        start = time.time()
        sit.pull_wait(20, poll=0.01)
        elapsed = time.time() - start
        self.assertLess(elapsed, 5)          # back long before the 20 s wait
        self.assertIsNotNone(sit.fight_start)
        starts = sit.marks.kinds("fight_start")
        self.assertEqual(len(starts), 1)
        self.assertTrue(starts[0].get("during_pull_wait"))
        self.assertGreater(starts[0].get("early_s"), 0)
        self.assertEqual(starts[0].get("mobs"), [LIVE])

    def test_pull_wait_quiet_waits_full_and_stamps_nothing(self):
        agent = FaceAgent()
        agent.unit_list = [{"guid": LIVE, "in_combat": False, "dead": False}]
        sit = make_sit(agent, [LIVE])
        start = time.time()
        sit.pull_wait(0.2, poll=0.01)
        self.assertGreaterEqual(time.time() - start, 0.2)
        self.assertIsNone(sit.fight_start)
        self.assertEqual(sit.marks.kinds("fight_start"), [])

    def test_pull_wait_stops_on_abort(self):
        agent = FaceAgent()
        sit = make_sit(agent, [LIVE])
        sit.abort = lambda: "slot gone"
        start = time.time()
        sit.pull_wait(20, poll=0.01)
        self.assertLess(time.time() - start, 5)
        self.assertIsNone(sit.fight_start)
        self.assertEqual(sit.marks.kinds("fight_start"), [])
    def test_pull_wait_retries_a_failed_unit_read_and_still_stamps(self):
        # round 1 HIGH: a transient RpcError from fighting() is retried on the
        # next poll, not a repeat abort; the early stamp still lands
        agent = FaceAgent()
        sit = make_sit(agent, [LIVE])
        calls = []

        def flaky(mobs):
            calls.append(1)
            if len(calls) == 1:
                raise agent_mod.RpcError("units: rpc failed")
            return True

        sit.fighting = flaky
        self.assertEqual(sit.pull_wait(20, poll=0.01), "fight")
        self.assertIsNotNone(sit.fight_start)
        self.assertTrue(sit.fight_seen)
        self.assertEqual(len(sit.marks.kinds("fight_start")), 1)

    def test_pull_wait_aborts_at_once_when_the_read_dies_with_the_session(self):
        # round 2 HIGH: a read that fails because the session/lease is gone is not a
        # transient poll failure: the wait ends at once, never a retry
        agent = FaceAgent()
        sit = make_sit(agent, [LIVE])
        reads = []

        def dead_session(mobs):
            reads.append(1)
            sit.abort = lambda: "lease lost: another slot took it"
            raise agent_mod.RpcError("units: rpc failed")

        sit.fighting = dead_session
        start = time.time()
        self.assertEqual(sit.pull_wait(20, poll=0.01), "aborted")
        self.assertLess(time.time() - start, 5)
        self.assertEqual(len(reads), 1)          # the abort is not retried
        self.assertIsNone(sit.fight_start)
        self.assertEqual(sit.marks.kinds("fight_start"), [])



class FightDeadlineTest(unittest.TestCase):
    def test_fight_deadline_uses_early_stamp(self):
        sit = make_sit(FaceAgent(), [LIVE])
        self.assertIsNone(sit.fight_deadline(60))
        sit.fight_start = 1000.0
        self.assertEqual(sit.fight_deadline(60), 1060.0)


class FacingTest(unittest.TestCase):
    def live_and_dead(self, agent):
        agent.unit_list = [{"guid": LIVE, "hostile": True, "dead": False, "level": 41},
                           {"guid": DEAD, "hostile": True, "dead": True, "level": 41}]
        return make_sit(agent, [DEAD, LIVE])

    def test_threat_faces_live_summon_then_taunts(self):
        agent = FaceAgent()
        sit = self.live_and_dead(agent)
        sit.threat()
        seq = [(m, (p or {}).get("guid") if m in ("face", "target") else (p or {}).get("spell_id"))
               for m, p in agent.calls if m in ("face", "target", "cast")]
        self.assertEqual(seq, [("face", LIVE), ("target", LIVE), ("cast", 355)])

    def test_attack_faces_first(self):
        agent = FaceAgent()
        sit = make_sit(agent, [LIVE])
        sit.attack(LIVE)
        kinds = [m for m, _ in agent.calls]
        self.assertIn("face", kinds)
        self.assertLess(kinds.index("face"), kinds.index("attack"))
        self.assertEqual([(p or {}).get("guid") for m, p in agent.calls if m == "face"],
                         [LIVE])

    def test_face_error_still_casts(self):
        agent = tl.FakeAgent()    # face answers {"_err": ...}, like a refused GM line
        sit = self.live_and_dead(agent)
        sit.threat()
        self.assertEqual([c["spell_id"] for c in agent.casts], [355])
        sit.attack(LIVE)
        self.assertEqual(agent.attacks, 1)

    def test_threat_skips_the_marked_cc_mob(self):
        # round 1 HIGH: threat() never targets/Taunts the trial's CC mark; with
        # summoned[0] dead it picks the next live UNMARKED summon
        marked = norm("0xF13000000000ABCF")
        agent = FaceAgent()
        agent.unit_list = [{"guid": marked, "hostile": True, "dead": False, "level": 41},
                           {"guid": DEAD, "hostile": True, "dead": True, "level": 41},
                           {"guid": LIVE, "hostile": True, "dead": False, "level": 41}]
        sit = make_sit(agent, [marked, DEAD, LIVE])
        sit.ctx.guids["marked"] = marked
        sit.threat()
        seq = [(m, (p or {}).get("guid") if m in ("face", "target") else (p or {}).get("spell_id"))
               for m, p in agent.calls if m in ("face", "target", "cast")]
        self.assertEqual(seq, [("face", LIVE), ("target", LIVE), ("cast", 355)])

    def test_threat_skips_when_only_the_mark_is_alive(self):
        marked = norm("0xF13000000000ABCF")
        agent = FaceAgent()
        agent.unit_list = [{"guid": marked, "hostile": True, "dead": False, "level": 41}]
        sit = make_sit(agent, [marked])
        sit.ctx.guids["marked"] = marked
        sit.threat()
        self.assertEqual(agent.casts, [])
        self.assertEqual([m for m, _ in agent.calls if m == "target"], [])

    def test_attack_refuses_the_marked_cc_mob(self):
        marked = norm("0xF13000000000ABCF")
        agent = FaceAgent()
        sit = make_sit(agent, [LIVE, marked])
        sit.ctx.guids["marked"] = marked
        sit.attack(marked)
        self.assertEqual(agent.attacks, 0)
        self.assertEqual([m for m, _ in agent.calls if m == "target"], [])

class RecordingGuard:
    """A guard that records the send() lines instead of reaching the game."""

    def __init__(self):
        self.sent = []

    def send(self, kind, target=None, *args):
        self.sent.append((kind, target) + tuple(args))
        return {}


def make_run_sit(agent, trial, guard=None):
    """A Situation wired for run(): an arena and a summon, nothing touching the game."""
    tmp = tempfile.mkdtemp()
    led = tl.new_ledger(tmp)
    led.add({"kind": "summon", "guid": LIVE})
    marks = tl.FakeMarks()
    collector = tl.StubCollector()
    sit = situations.Situation(agent, trial, guard, led, marks, collector,
                               situations.SitContext(player_guid=tl.PLAYER),
                               arenas=[], mobs={})
    sit.acquire_arena = lambda: {"id": "a1"}

    def summon(role, count, near_player=True):
        sit.summoned.append(LIVE)
        return [LIVE]
    sit.summon = summon
    collector.last_sample = {"player": {"health": 900, "max_health": 1000,
                                        "in_combat": True, "auras": []}}
    return sit, marks, collector


class RunWiringTest(unittest.TestCase):
    """run() executes the pull_wait -> fight_deadline path (round 1 MEDIUM).

    Combat starts during pull_after_s and is gone before the first fight-loop
    tick: the rep still scores off the early stamp (fight_start set, no
    "no_fight"), the deadline runs from it, and the marks carry
    during_pull_wait + early_s for the card's early_fight= line.
    """

    def test_early_combat_during_the_wait_scores_off_the_early_stamp(self):
        agent = FaceAgent()
        agent.unit_list = [{"guid": LIVE, "hostile": True, "dead": False, "level": 41,
                            "in_combat": True}]
        trial = make_trial()
        trial["situation"] = {"kind": "tank_damage", "pull_after_s": 0.3,
                              "mobs": {"role": "melee", "count": 1, "refill": False}}
        trial["duration_s"] = 2
        sit, marks, _ = make_run_sit(agent, trial)
        polls = []

        def fighting_once(mobs):
            # in combat during pull_wait, gone by the first loop tick
            polls.append(1)
            return len(polls) == 1
        sit.fighting = fighting_once
        out = sit.run()
        self.assertTrue(out["ok"], out)
        self.assertNotEqual(out["ended"], "no_fight", out)
        self.assertIsNotNone(out["fight_start"], out)
        self.assertTrue(sit.fight_seen)
        starts = marks.kinds("fight_start")
        self.assertEqual(len(starts), 1)
        self.assertTrue(starts[0].get("during_pull_wait"))
        self.assertGreater(starts[0].get("early_s"), 0)


class AbortDuringWaitRunTest(unittest.TestCase):
    """Round 2 HIGH: a session/lease lost during pull_after_s ends the repeat at once.

    The read that dies with the session is not retried, and run() sends nothing
    after it: no debuff strip, no pull/attack, no debuff apply, no governor.
    """

    def test_abort_during_the_wait_ends_the_repeat_before_any_command(self):
        agent = FaceAgent()
        agent.unit_list = [{"guid": LIVE, "hostile": True, "dead": False, "level": 41}]
        guard = RecordingGuard()
        trial = make_trial()
        trial["situation"] = {"kind": "debuff", "pull_after_s": 0.3,
                              "debuff": {"spell_id": 770},
                              "mobs": {"role": "melee", "count": 1, "refill": False}}
        trial["duration_s"] = 2
        sit, marks, collector = make_run_sit(agent, trial, guard=guard)
        reads = []

        def dead_session(mobs):
            reads.append(1)
            sit.abort = lambda: "lease lost: another slot took it"
            raise agent_mod.RpcError("units: rpc failed")

        sit.fighting = dead_session
        out = sit.run()
        self.assertFalse(out["ok"], out)
        self.assertEqual(out["ended"], "lease lost: another slot took it")
        self.assertEqual(out["invalid_reason"], "lease lost: another slot took it")
        self.assertEqual(len(reads), 1)              # the abort is not a retry
        self.assertEqual(guard.sent, [])             # no strip, no debuff apply
        self.assertEqual([m for m, _ in agent.calls
                          if m in ("attack", "target", "face", "walk_to")], [])
        self.assertIsNone(sit.fight_start)
        self.assertEqual(marks.kinds("fight_start"), [])
        ends = marks.kinds("fight_end")
        self.assertEqual(len(ends), 1)
        self.assertEqual(ends[0]["ended"], "lease lost: another slot took it")
        self.assertEqual(collector.tick_hooks, [])

    def test_a_plain_read_failure_during_the_wait_is_retried(self):
        # the same wiring, a read failure with no abort: retried, and the repeat runs
        agent = FaceAgent()
        agent.unit_list = [{"guid": LIVE, "hostile": True, "dead": False, "level": 41}]
        trial = make_trial()
        trial["situation"] = {"kind": "tank_damage", "pull_after_s": 0.3,
                              "mobs": {"role": "melee", "count": 1, "refill": False}}
        trial["duration_s"] = 1
        sit, marks, _ = make_run_sit(agent, trial)
        calls = []

        def flaky(mobs):
            calls.append(1)
            if len(calls) == 1:
                raise agent_mod.RpcError("units: rpc failed")
            return True
        sit.fighting = flaky
        out = sit.run()
        self.assertTrue(out["ok"], out)
        self.assertEqual(len(calls), 2)
        starts = marks.kinds("fight_start")
        self.assertEqual(len(starts), 1)
        self.assertTrue(starts[0].get("during_pull_wait"))


if __name__ == "__main__":
    unittest.main()
