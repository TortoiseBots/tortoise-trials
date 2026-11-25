<img width="2752" height="1536" alt="Tortoise Trials" src="https://github.com/user-attachments/assets/682830ac-7313-4af6-bd25-93e7c9e509cc" />

# Tortoise Trials

A behaviour test bench for **TortoiseBots**. A real [`turtle-agent`](https://github.com/TortoiseBots/turtle-agent)
player plays alongside a hired TortoiseBots bot in a controlled scenario, and rules citing the exact bot code
(`file:line`) score what the bot did and compare before/after runs.

> [!WARNING]
> **Test servers only.** Never point this tool at a live server. The runner queries `turtle-agent` for its allowlist of
> test servers and refuses any other server name (exit `4`).

Nothing here modifies the bots — it sets up a situation on a test server, records telemetry, scores behaviour, and
generates before/after comparison blocks for pull requests.

## Requirements

- **Python 3.11+**, standard library only.
- [`turtle-agent`](https://github.com/TortoiseBots/turtle-agent) built with `lease` and `slot setup` (on `PATH`, or
  via `--binary` / `TRIALS_BINARY`).
- A **TortoiseBots test server** with the Eluna test toolkit and a GM account for the player character.

## Quick start

```bash
./trials.sh list [--class priest]
./trials.sh validate [files...]
./trials.sh run --server my-test-server --trial priest-holy-pws-def-arms --label before [--repeats 4] [--parallel 2]
./trials.sh compare runs/<after> --baseline runs/<before>
./trials.sh pr-block --before runs/<before> --after runs/<after> --issue 1553
./trials.sh cleanup <run-dir>
```

- `trials run` requires a **detached HEAD** with no modified tracked files (override for emergencies:
  `TRIALS_ALLOW_UNPINNED=1`).
- Run artifacts (`RUN.json`, `events.jsonl`, `setup.json`, `verdicts.json`, `card.md`/`card.json`) are written under
  `./runs` (or `TRIALS_OUT`).

## Documentation

Full documentation lives under [`knowledge/`](knowledge/index.md):

| Area | Topics |
|---|---|
| [Operations](knowledge/operations/index.md) | [Configuration & Env](knowledge/operations/configuration.md), [Running, Scoring & PR Blocks](knowledge/operations/running.md) |
| [Trial Format & Scoring](knowledge/trials/index.md) | [Trial JSON Format](knowledge/trials/format.md), [Variants & Player Gear](knowledge/trials/variants-and-gear.md), [Scoring Rule Options](knowledge/trials/scoring-rules.md) |
| [Reliability & Limits](knowledge/reliability/index.md) | [Validity Guards & Summons](knowledge/reliability/validity-guards.md), [Known Limits & Offline Tests](knowledge/reliability/known-limits.md) |

Design rationale and tracked follow-ups live in [`DECISIONS.md`](DECISIONS.md) and [`FOLLOWUPS.md`](FOLLOWUPS.md).

## Tests

```bash
python3 -m unittest discover -s tests
python3 -I trials.py validate
```

## Licence

Licensed under **AGPL-3.0-or-later** ([`LICENSE`](LICENSE), [`NOTICE`](NOTICE)), as `turtle-agent`.

This is an unofficial community project made for educational purposes. It is not affiliated with Turtle WoW or Blizzard
Entertainment.
