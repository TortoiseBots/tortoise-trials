---
type: Reference
title: Trial File Format
description: Trial JSON schema, situation mechanics, setup checks, opportunity windows, and offline data files.
tags: [trials, schema, json, situations]
status: stable
generated: { by: "antigravity/gemini", at: "2026-11-25T14:35:00Z" }
sources:
  - id: trial-example
    resource: trials/healers/priest-holy-pws-def-arms-2tank.json (example healer trial)
    title: Example 2-tank Holy priest trial
  - id: build-data
    resource: build_data.py (offline SQL data builder)
    title: Offline data builder
---

# Schema

Each trial is a single JSON file under `trials/<group>/`. Unknown keys are rejected by `trials.sh validate`.

- **`player`:** Class, level, talents (tree and spell IDs), stance, forced role, setup `auras` (applied after stance and polled; missing auras fail `player_auras`), items, and `gear` (`null` or `"tier"`, see [Variants and Player Gear](variants-and-gear.md)). Never put a measured debuff in `player.auras`; use `situation.debuff`.
- **`bot` and `extra_bots`:** Class, spec, role, level, gear tier, items. An `extra_bots` entry with `gear` (e.g. `"blue"`) triggers `autogear <name> <gear>` and fails `extra_bots_role` if re-gearing does not confirm.
- **`situation`:** Driven by `kind` (`tank_damage`, `ooc_hurt`, `ooc_buffs`, `cc_target`, etc.):
  - Mob spec (`mobs`), target `hp_band`, `floor_pct`, pull delay, and optional `top_up_to_pct` (non-ooc kinds).
  - `reset_hire_cooldowns: true` runs `.cooldown` before first summon (check `hire_cooldowns_reset`; does not clear item cooldowns such as Thistle Tea or Greater Mana Potion).
  - `min_rep_gap_s` waits between the previous repeat's last `Restore Mana` potion wall time and the next repeat's start (e.g. `130` s for the 120 s potion cooldown). Unreadable prior telemetry receives the full wait; a carried-over potion scores `INCONCLUSIVE` (`item cooldown from rep N-1`).
  - `energy_drain {first_at_s 5-170, every_s >= 20, to 0-19}` (rogue `tank_damage` only) drains the hire's energy on schedule and writes `energy_drain` marks.
  - `prepull_unaura: [<aura_id>, ...]` strips persistent forms (e.g. Shadowform `15473`) from reused hires before pull; failure or unreadable aura state makes the repeat `INVALID`.
  - `debuff {spell_id: <id>}` proves absence before pull, stamps `fight_start` (`t = 0`), then applies the measured debuff in combat and verifies a fresh `aura_applied` event (retries once; otherwise `INVALID`).
  - `ooc_buffs` runs `.unaura all` on the player and on the hire only when no Drink/Food aura is active (waits up to 30 s for meals, restores `bot.mana_pct` via `.modify mana` afterward; unresolved meal, unknown aura list, or failed mana reset makes the repeat `INVALID`).
- **`setup_checks`:** Pre-scoring invariants verified before a repeat counts (see [Validity Guards](../reliability/validity-guards.md)).
- **`opportunity`:** Defines when the bot had a reason to act (`unit`, `hp_lt`/`hp_gt`, `in_combat`, `has_aura`).
- **`rules`:** Each rule defines `id`, `source` (`file:line` in bot code), `expect_today`, `why_expect`, `check` (`count`, `ratio`, `latency`, `uptime`, `first`, `rate`, `walk_metric`), `pass_if`, `min_opportunity_s`, `min_reps`, and optional `pool: true` (see [Scoring Rule Options](scoring-rules.md)).

Spell, item, and creature IDs come from `data/` (built offline from public core SQL via `build_data.py`). Generic character names live in `data/characters.json` (`Trl*`).[^build-data]

# Examples

Shortened excerpt from `trials/healers/priest-holy-pws-def-arms-2tank.json`:[^trial-example]

```json
{
  "id": "priest-holy-pws-def-arms-2tank",
  "class": "priest", "spec": "holy",
  "player": {"class": "warrior", "level": 40, "stance": 71,
             "talents": {"tree": "arms", "spells": [16462, 12286]}},
  "bot": {"class": "priest", "spec": "holy", "role": "healer", "level": 40, "gear": "blue"},
  "extra_bots": [{"class": "paladin", "spec": "protection", "role": "tank", "level": 40}],
  "situation": {"kind": "tank_damage", "mobs": {"role": "melee", "count": 1, "refill": true},
                "hp_band": [40, 90], "floor_pct": 12, "victim": "player"},
  "opportunity": {"unit": "$player", "hp_lt": 90, "hp_gt": "$critical", "in_combat": true},
  "rules": [{"id": "PRI-PWS-DEF-ARMS-2TANK", "source": "ai/playerbot/AiFactory.cpp:520-576,597-611",
             "expect_today": "PASS",
             "check": {"metric": "count", "where": {"kind": "cast", "src": "$bot", "dst": "$player",
                       "spell": "Power Word: Shield", "dst_hp_gt": "$critical", "in_combat": true}},
             "pass_if": "== 0", "min_opportunity_s": 90}]
}
```

Related: [Variants and Player Gear](variants-and-gear.md), [Scoring Rule Options](scoring-rules.md).

[^trial-example]: Example 2-tank Holy priest trial
[^build-data]: Offline data builder
