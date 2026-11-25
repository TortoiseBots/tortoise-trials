---
type: Reference
title: Variants and Player Gear
description: Variant overrides, tier gear kits, proficiency learning, and guarded GM command templates.
tags: [variants, gear, gm-guard, trials]
status: stable
generated: { by: "antigravity/gemini", at: "2026-11-25T14:35:00Z" }
sources:
  - id: gear-py
    resource: trl/gear.py (player gear kits and proficiency tables)
    title: Gear kit helper
  - id: decisions
    resource: DECISIONS.md (level >= 35 hire rule and design rationale)
    title: Architecture decisions log
---

# Trial Variants

A trial may define up to 6 named `variants` (raid trials take none) to test the same behaviour at another level, kit, or spec:

```json
"variants": [
  {"name": "lvl60", "title": "level 60",
   "override": {"level": 60, "player": {"gear": null}, "situation": {"mobs": {"level_delta": -2}}}}
]
```

- **Merge semantics:** `override` accepts `level` (shortcut setting `player.level`, `bot.level`, and all `extra_bots[].level`; explicit fields win), `player`, `bot`, `extra_bots`, `situation`, and `rules`. Dicts merge key-by-key, lists/scalars replace whole, and `null` clears a field.
- **Rule overrides:** `rules` maps `RULE-ID` to threshold overrides (`pass_if`, `min_n`, `min_opportunity_s`, `min_reps`) for existing rules only. A `bot.spec` variant may also rewrite `desc`, `source`, `why_expect`, and `check` per existing rule ID.
- **Constraints:** `player.class`, `bot.class`, and `bot.role` cannot change. Hires must be level `>= 35` so `bot_talents` can verify marker talents.[^decisions]
- **Identity:** Each variant becomes `<trial>@<variant>` with its own run folder, `trial.json`, card rows, and `(trial_id, rule_id)` diff key in `compare` and `pr-block`.

# Player Gear (`player.gear: "tier"`)

Ungeared GM-levelled players generate far less threat than real tanks, causing DPS bots to throttle constantly. Setting `"gear": "tier"` equips a deterministic vanilla kit before the repeat (`setup_check`: `player_gear`):[^gear-py]

- **Kit source:** `data/gear_kits.json` (built by `build_data.py` from `item_template`), currently warrior `tank` (plate + 1H + shield when `forced_role == "tank"`) and `dps` (plate + 2H, no shield) at levels 40, 45, and 50 (intermediate levels pick the highest kit at most 9 levels below). Items are plain vanilla entries (`< 20000`, excluding TBC-scale customs), no procs/on-use, no int/spirit, and no rep/honor/profession requirements.
- **Equip flow:** Learns required armor/weapon proficiencies via guarded self-only `.learn` (from fixed tables in `trl/gear.py`), strips carryover kit items from other levels (`player_gear_carryover`), keeps worn items, equips bag copies, and grants missing pieces via guarded self-only `.additem` (`additem_self`). Verified via the agent's `equipment` read.
- **Strip on non-gear trials:** Trials without `player.gear` strip all kit entries from worn slots and bags (`player_gear_strip`, `.additem <id> -1`) while preserving non-kit starting gear.

# Guarded GM Command Kinds

All GM commands pass through a closed template guard bound to target classes (e.g. `modify_energy {cur} {max}` for hires only; `.cooldown` for player or hire when `reset_hire_cooldowns` is enabled; `additem_self` restricted to kit entries on the player itself).

Related: [Trial File Format](format.md), [Running, Scoring, and Comparisons](../operations/running.md).

[^gear-py]: Gear kit helper
[^decisions]: Architecture decisions log
