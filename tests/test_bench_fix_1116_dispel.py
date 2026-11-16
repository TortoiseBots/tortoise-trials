"""Bench round 1116: the dispel-magic setup order and the tested-debuff contract.

Fail-first: each case failed on the base commit (old code) and passes with the fix.

- DispelSetupOrderTest pins the setup read-back: check_player_auras waits for a
  wanted aura to land before reading it back (bounded, polling) and re-sends only
  a still-missing aura once.
- DispelRunOrderTest drives Situation.run with a fake agent and asserts the call
  order (the tested debuff is stripped before the pull and applied after it) and
  the retry path (no fresh `aura_applied` on the first apply -> one more apply;
  still none -> INVALID; a strip that cannot land -> INVALID before the pull).
"""

import os
import sys
import tempfile
import unittest
import unittest.mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

import test_live as tl  # noqa: E402
from trl.live import agent as agent_mod  # noqa: E402
from trl.live import setup as setup_mod  # noqa: E402
from trl.live import situations  # noqa: E402


PLAYER = "0x0000000000000001"
BOT = "0x0000000000000002"
MOB = "0xf13000000000abcd"


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

    def _guard(self, agent):
        from trl.live import gm_guard
        from trl.live.ledger import Ledger
        tmp = tempfile.mkdtemp()
        ctx = gm_guard.GmContext(player_guid=FakeAgent.PLAYER, aura_ids=frozenset({71, 770}))
        return gm_guard.GmGuard(agent, Ledger(os.path.join(tmp, "l.jsonl")), ctx), ctx

    def test_missing_aura_is_retried_once_then_proven(self):
        agent = FakeAgent(auras=[71])
        guard, ctx = self._guard(agent)
        calls = []

        orig_send = guard.send

        def send(kind, target=None, *args):
            calls.append((kind, args[0] if args else None))
            return orig_send(kind, target, *args)

        guard.send = send
        row = setup_mod.check_player_auras(agent, self.trial(), guard, ctx, timeout=0.05, poll=0.01)
        self.assertTrue(row["ok"], row)
        self.assertEqual(sorted(row["value"]), [71, 770])
        # one send per wanted aura, then the retry of the missing 770 only.
        self.assertEqual([c[1] for c in calls if c[0] == "aura"], [770, 770])

    def test_still_missing_after_the_retry_fails(self):
        class DropAura(FakeAgent):
            def rpc(self, method, params=None, timeout=None):
                if method == "gm" and (params or {}).get("text", "").startswith(".aura 770"):
                    return {}
                return FakeAgent.rpc(self, method, params, timeout)

        agent = DropAura(auras=[71])
        guard, ctx = self._guard(agent)
        row = setup_mod.check_player_auras(agent, self.trial(), guard, ctx, timeout=0.05, poll=0.01)
        self.assertFalse(row["ok"])
        self.assertIn("missing [770]", row["evidence"])

    def test_the_read_back_waits_for_the_aura_instead_of_resending(self):
        # `.aura` lands a tick later (the live server is asynchronous): a single immediate
        # read proved nothing and the old code re-sent into the same stale read, failing setup.
        class Late(FakeAgent):
            def __init__(self):
                FakeAgent.__init__(self)
                self.reads = 0

            def own_row(self):
                self.reads += 1
                auras = [{"spell_id": 770}] if self.reads > 2 else []
                return {"guid": self.PLAYER, "auras": auras}

            def rpc(self, method, params=None, timeout=None):
                # the line lands, the read-back is stale for two polls: exactly one send
                if method == "gm":
                    self.gm.append((params or {}).get("text") or "")
                    return {}
                return FakeAgent.rpc(self, method, params, timeout)

        agent = Late()
        guard, ctx = self._guard(agent)
        row = setup_mod.check_player_auras(agent, self.trial(), guard, ctx, timeout=1.0, poll=0.01)
        self.assertTrue(row["ok"], row)
        self.assertEqual(agent.gm, [".aura 770"])


class DispelRunAgent(tl.FakeAgent):
    """A FakeAgent whose event log answers `since` and can hold the `aura_applied` back."""

    def __init__(self):
        tl.FakeAgent.__init__(self)
        self.seq = 0
        self.event_rows = []
        self.aura_sends = 0
        self.land_on = 1        # the `.aura` send that emits the fresh `aura_applied`
        self.attacked = []

    def emit_aura_on(self, spell_id, target):
        self.seq += 1
        self.event_rows.append({"seq": self.seq, "kind": "aura_applied", "spell_id": int(spell_id),
                                "target": {"guid": agent_mod.norm_guid(target)}})

    def rpc(self, method, params=None, timeout=None):
        params = params or {}
        if method == "events":
            since = params.get("since")
            if since == agent_mod.HEAD_PROBE:
                return {"events": [], "next": self.seq, "oldest": 0, "dropped": False}
            rows = [r for r in self.event_rows if r["seq"] > int(since or 0)]
            return {"events": rows, "next": self.seq, "oldest": 0, "dropped": False}
        if method == "attack":
            self.attacked.append("attack")
        return tl.FakeAgent.rpc(self, method, params, timeout)


class OrderGuard:
    """A guard double that records every line and settles the fake world with it."""

    def __init__(self, agent, order):
        self.agent = agent
        self.order = order

    def send(self, kind, target=None, *args):
        self.order.append((kind, target) + tuple(args))
        spell = args[0] if args else None
        row = self.agent.unit_rows.get(PLAYER)
        if not isinstance(row, dict):
            return "sent"
        auras = [a.get("spell_id") for a in (row.get("auras") or [])]
        if kind == "unaura":
            row["auras"] = [{"spell_id": a} for a in auras if a != int(spell)]
        elif kind == "aura":
            self.agent.aura_sends += 1
            if int(spell) not in auras:
                row["auras"] = [{"spell_id": a} for a in auras + [int(spell)]]
            if self.agent.aura_sends == self.agent.land_on:
                self.agent.emit_aura_on(int(spell), target)
        return "sent"


class DispelRunOrderTest(unittest.TestCase):
    """The tested debuff is not a setup aura: absent before the pull, fresh after it."""

    def build(self, auras=(), land_on=1):
        agent = DispelRunAgent()
        trial = {"id": "t", "player": {"level": 40, "class": "warrior"},
                 "situation": {"kind": "debuff", "debuff": {"spell_id": 770},
                               "mobs": {"role": "melee", "count": 1}}}
        order = []
        guard = OrderGuard(agent, order)
        sit = situations.Situation(agent, trial, guard, tl.new_ledger(tempfile.mkdtemp()),
                                   tl.FakeMarks(), tl.StubCollector(),
                                   situations.SitContext(player_guid=PLAYER, bot_name="Helper",
                                                         hire_guid=BOT),
                                   arenas=[], mobs={})
        agent.unit_rows[PLAYER] = {"guid": PLAYER, "auras": [{"spell_id": a} for a in auras],
                                   "health": 1000, "max_health": 1000, "level": 40}
        lo, _hi = sit.level_window()
        agent.unit_rows[MOB] = {"guid": MOB, "hostile": True, "dead": False, "level": lo,
                                "health": 500, "max_health": 500, "in_combat": True}
        agent.land_on = land_on
        sit.acquire_arena = lambda: {"id": "a1"}

        def summon(role, count, near_player=True):
            sit.summoned.append(MOB)
            return [MOB]
        sit.summon = summon
        real_pull = sit.pull

        def pull():
            order.append("pull")
            real_pull()
        sit.pull = pull
        sit.abort = lambda: "stop at once"       # the fight loop ends on its first pass
        return sit, agent, order

    def test_a_leftover_debuff_is_stripped_before_the_pull_and_applied_after_it(self):
        sit, agent, order = self.build(auras=[770])
        sit.run()
        self.assertEqual(order[0], ("unaura", PLAYER, 770))
        self.assertEqual(order[1], "pull")
        applied = [i for i, row in enumerate(order) if row != "pull" and row[0] == "aura"]
        self.assertEqual(len(applied), 1, order)
        self.assertGreater(applied[0], order.index("pull"))
        self.assertEqual(order[applied[0]], ("aura", PLAYER, 770))
        self.assertEqual(agent.aura_sends, 1)
        kinds = [r.get("kind") for r in sit.marks.rows]
        self.assertIn("debuff_stripped", kinds)
        self.assertIn("debuff_applied", kinds)

    def test_an_absent_debuff_is_not_unauraed_and_lands_after_the_pull(self):
        sit, agent, order = self.build(auras=[])
        sit.run()
        self.assertEqual(order[0], "pull")
        self.assertEqual([r for r in order if r != "pull" and r[0] == "unaura"], [])
        applied = [i for i, row in enumerate(order) if row != "pull" and row[0] == "aura"]
        self.assertEqual(len(applied), 1, order)
        self.assertGreater(applied[0], 0)
        self.assertIn("debuff_absent", [r.get("kind") for r in sit.marks.rows])

    def test_a_refresh_without_a_fresh_aura_on_is_retried_once(self):
        sit, agent, order = self.build(land_on=2)
        with unittest.mock.patch.object(situations, "DEBUFF_AURA_WAIT_S", 0.01):
            sit.run()
        applied = [row for row in order if row != "pull" and row[0] == "aura"]
        self.assertEqual(len(applied), 2, order)          # the retry ran
        self.assertEqual(agent.aura_sends, 2)
        done = sit.marks.kinds("debuff_applied")
        self.assertEqual(len(done), 1)
        self.assertEqual(done[0]["attempt"], 2)

    def test_no_fresh_aura_on_after_the_retry_makes_the_repeat_invalid(self):
        sit, agent, _order = self.build(land_on=99)
        with unittest.mock.patch.object(situations, "DEBUFF_AURA_WAIT_S", 0.01):
            out = sit.run()
        self.assertFalse(out["ok"])
        self.assertEqual(out["ended"], "debuff")
        self.assertIn("no fresh aura_on", out["invalid_reason"])
        self.assertEqual(agent.aura_sends, 2)
        attempts = [r["attempt"] for r in sit.marks.kinds("debuff_apply")]
        self.assertEqual(attempts, [1, 2])

    def test_a_debuff_still_up_after_the_unaura_makes_the_repeat_invalid(self):
        sit, agent, order = self.build(auras=[770])

        class NoUnaura(OrderGuard):
            def send(self, kind, target=None, *args):
                if kind == "unaura":
                    self.order.append((kind, target) + tuple(args))
                    return "sent"
                return OrderGuard.send(self, kind, target, *args)

        sit.guard = NoUnaura(agent, order)
        with unittest.mock.patch.object(situations, "PREPULL_AURA_WAIT_S", 0.01):
            out = sit.run()
        self.assertFalse(out["ok"])
        self.assertEqual(out["ended"], "prepull")
        self.assertIn("still up", out["invalid_reason"])
        self.assertEqual(agent.attacked, [])
        self.assertTrue(sit.marks.kinds("debuff_strip_failed"))


if __name__ == "__main__":
    unittest.main()
