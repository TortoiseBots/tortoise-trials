---
type: Reference
title: Scoring Rule Options
description: Latency triggers, responder cooldown debouncing, mark exclusions, pooling, and party_under_attack.
tags: [rules, scoring, latency, pooling, debounce]
status: stable
generated: { by: "antigravity/gemini", at: "2026-11-25T14:35:00Z" }
sources:
  - id: scorer
    resource: trl/ (rule scoring and verdict aggregation)
    title: Rule scoring engine
---

# Trigger and Debounce Options

- **`check.trigger` marks (latency rules):** `{"kind": "mark", "mark": "<mark kind>"}` triggers latency scoring from runner marks (e.g. `energy_drain`) on the event time base inside the scored window.[^scorer]
- **`check.debounce_responder_s`:** Skips latency triggers arriving within `N` s after the bot's last matching response (e.g. 10 s for Taunt, 30 s for Counterspell), avoiding double-penalizing one cooldown. Skipped triggers do not start per-source `trigger_debounce_s`.
- **`check.debounce_responder_spells`:** Restricts which answered spells start the responder cooldown (e.g. Taunt starts the 10 s cooldown, Mocking Blow does not).
- **`check.debounce_responder_across_reps: true`:** Carries responder cooldown across repeat boundaries for item cooldowns `.cooldown` cannot reset (such as 5-minute Thistle Tea or 120 s Greater Mana Potion, which is also accepted from `t - 2` during the pull). On `first` rules, full-window cooldown coverage yields `INCONCLUSIVE`; partial overlap still scores.
- **`check.skip_trigger_while`:** `{"unit": <alias>, "power_below_pct": N, "skip_when_dead": true}` (cross-trigger latency rules) skips triggers while the answering unit is below `N`% power or dead (including Spirit of Redemption).
- **`situation.damage_interval_s`:** (`tank_damage` only, 4-60 s, default `4`) Spaces governor re-damage so healer mana lasts the repeat.

# Filtering and Aggregation Options

- **`check.where.not_within_s_after_mark`:** `{"kind": "<mark kind>", "s": N}` (or a list) drops events/samples within `N` s after runner marks in `marks.jsonl` (such as `refill` or `fight_start`) and adjusts `min_opportunity_s` accordingly while preserving full samples for HP/aura/combat lookups.
- **`pool: true`:** Computes a single trial verdict from summed `sum(k) / sum(n)` across valid repeats, applying `min_n` to the pooled `n` instead of per-repeat `n`. Any repeat with `INCONCLUSIVE` reason `attack state unknown` makes the pooled verdict `INCONCLUSIVE`. `min_reps` still applies.
- **`check.where.party_under_attack`:** Non-empty list of party aliases (e.g. `["$player", "$extras"]`). Counts events only while a listed party member has a hostile `mob:` attacker (bot itself is not implied). Combines newest attack packets (`attack_start`/`attack_stop`) with sample `target` within a 5 s liveness window; a live mob with no target sample leaves the state unknown and scores `count` rules `INCONCLUSIVE` rather than `PASS`. Used by `TNK-PAL-NO-DRINK-UNDER-ATTACK` as a cast-time regression guard.

Related: [Trial File Format](format.md), [Validity Guards and Mob Claiming](../reliability/validity-guards.md).

[^scorer]: Rule scoring engine
