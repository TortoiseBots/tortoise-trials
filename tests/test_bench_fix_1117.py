"""Bench fix 1117: pull_wait early-combat stamp, fight_deadline, facing threat/attack.

Fail-first: each case failed on the base commit (no pull_wait/fight_deadline
methods, threat()/attack() never face, no early_fight on the card) and passes
with the fix.
"""

import inspect
import os
import sys
import tempfile
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

import test_live as tl  # noqa: E402
from trl import report as report_mod  # noqa: E402
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


class WiringTest(unittest.TestCase):
    def test_run_waits_with_pull_wait_and_the_card_shows_early_fight(self):
        src = inspect.getsource(situations.Situation.run)
        self.assertIn("pull_wait(", src)
        self.assertIn("fight_deadline(", src)
        self.assertNotIn("time.sleep(wait)", src)
        self.assertIn("early_fight=", inspect.getsource(report_mod._early_fight))


if __name__ == "__main__":
    unittest.main()
