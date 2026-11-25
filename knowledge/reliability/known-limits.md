---
type: Reference
title: Known Limits and Offline Tests
description: Tracked follow-ups, caveats, and offline test suite commands.
tags: [limits, followups, tests]
status: stable
generated: { by: "antigravity/gemini", at: "2026-11-25T14:35:00Z" }
sources:
  - id: followups
    resource: FOLLOWUPS.md (tracked engineering follow-ups)
    title: Follow-ups list
  - id: tests-dir
    resource: tests/ (offline unittest suite)
    title: Unit test suite
---

# Known Limits

Tracked in `FOLLOWUPS.md`:[^followups]

- `mobs.level_delta: 0` currently behaves as `+1` (seven trial files specify `0`).
- Cast events can carry a stale `dst_hp_pct` instead of reading health from the nearest sample.
- `ooc_hurt` count rules also count casts before the window opens.
- Extra repeats trigger on rescue-cap losses, and setup failures repeat the same way.
- Event and bot-event windows pair with repeats by position; a repeat missing a window shifts pairing.
- The bot-warrior control rejects any off-hand item rather than shields only.
- `tests/test_rules_healers.py::TwoTankTrialFilesTest` fails because the 2-tank trial lacks `max_rescues_per_min`.
- Some `why_expect` notes state the runner re-casts stance; only `ooc_hurt` does.
- The bot-event pull (`TRIALS_EVPULL`) is an external hook not shipped in this repository.

# Offline Tests

```bash
python3 -m unittest discover -s tests
python3 -I trials.py validate
```

No server is contacted.[^tests-dir] Tests requiring the bot source tree, talent DBC files, rule briefs, or event pull script are skipped unless `TRIALS_BOT_SRC`, `TRIALS_DBC_DIR`, `TRIALS_RULE_BRIEFS`, or `TRIALS_EVPULL` is set.

Related: [Validity Guards and Mob Claiming](validity-guards.md), [Configuration and Environment](../operations/configuration.md).

[^followups]: Follow-ups list
[^tests-dir]: Unit test suite
