---
type: Reference
title: Validity Guards and Mob Claiming
description: Pre-scoring guards, adaptive difficulty, controls, and summon claiming rules.
tags: [guards, validity, adaptive, summons, controls]
status: stable
generated: { by: "antigravity/gemini", at: "2026-11-25T14:35:00Z" }
sources:
  - id: live-runner
    resource: trl/live/ (live runner guards and summon ledger)
    title: Live runner implementation
---

# Validity Guards

A repeat that fails a guard is marked `INVALID` or `INCONCLUSIVE`, never `PASS` or `FAIL`:[^live-runner]

- **Player visible:** Bots skip hidden GMs. Within the first 30 s, only direct evidence passes (a hire casting/healing/buffing on the player, or a sampler row whose API `target` is the player). Nearby mob hits or bot attacks within 5 yd are diagnostic only; if they are the sole evidence, the repeat is `INVALID` (`visibility unproven`).
- **Opportunity:** Rules score only samples matching the `opportunity` block and require `min_opportunity_s`; insufficient opportunity produces `INCONCLUSIVE`.
- **Stance and setup:** Player stance, talents, forced role, level, shield state, bot level/role/spec/items, and group composition are read back and verified (`setup_checks`) before the repeat counts. Stance is also scored as an uptime rule where relevant.
- **GM selection confirm:** Before any GM command targeting a selected unit, the runner waits for server confirmation that the unit is selected; failure aborts the run with exit `5`.
- **Rescue cap and adaptive difficulty:** The runner heals the player at the health floor up to `N` times per minute. Hitting the cap marks the repeat `INVALID` and steps the next repeat down in difficulty (lower mob level, then fewer mobs and no refill), never stepping back up within the run (`situation.adaptive: false` disables this).
- **Controls:** Control trials hold the setup constant while flipping the one condition under test (e.g. Battle Stance, warrior hired as bot, out of combat) to prove rules are neither trivially passing nor trivially failing.

# Mob Summon Claiming

Each mob is summoned with `.npc summon` and claimed into the run ledger:

- Claimed by GUID when the core prints one in the reply; otherwise by a newly appeared unit of that entry.
- A single new unit is claimed anywhere inside the 30 yd scan.
- With two or more new units, only one within 3 yd is claimed; otherwise the summon stays `summon_unclaimed` and refilling stops so no untracked mob can escape `cleanup`.

Related: [Trial File Format](../trials/format.md), [Scoring Rule Options](../trials/scoring-rules.md), [Known Limits and Offline Tests](known-limits.md).

[^live-runner]: Live runner implementation
