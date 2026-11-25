---
type: Reference
title: Configuration and Environment
description: Requirements, slot leasing, environment variables, and login pacer state.
tags: [configuration, env, slots, operations]
status: stable
generated: { by: "antigravity/gemini", at: "2026-11-25T14:35:00Z" }
sources:
  - id: cli-runner
    resource: trials.py (CLI entrypoint and environment configuration)
    title: Bench CLI entrypoint
  - id: turtle-agent
    resource: https://github.com/TortoiseBots/turtle-agent
    title: turtle-agent binary and slot lease table
---

# Requirements

- **Python 3.11+**, standard library only.
- **`turtle-agent` binary** built with `lease` and `slot setup`, available on `PATH` or via `--binary` / `TRIALS_BINARY`.[^turtle-agent]
- **TortoiseBots test server** with the Eluna test toolkit (handles GM and `.bot` commands, mob summons, and position/health reads).
- **GM account** for the player character (driven by `turtle-agent`; bots are hired via `.bot` commands).

Never point the runner at a live server: it queries the binary for its list of test servers and refuses any other server name (exit `4`).

# Slot Leasing

No server credentials are stored in the repository. Pass `--server NAME` on the CLI; slots (account, character, port) come from `turtle-agent lease list <server> --json` (see `turtle-agent` for the slot table format and `--slots FILE`).[^cli-runner]

- The runner leases a free slot, runs `turtle-agent slot setup`, and releases the lease on completion.
- Reserved slots or slots with an existing listener are skipped. Slot `3` is reserved by default (`TRIALS_RESERVED_SLOTS="5,6"` or `""` overrides it).
- A login pacer stores timestamps and account names in `~/.local/state/` to keep concurrent runs under the realm's login rate limit.

# Schema

Environment variables (all optional):

| Variable | Meaning |
|---|---|
| `TRIALS_BINARY` | Path to `turtle-agent` (`--binary` takes precedence) |
| `TRIALS_OUT` | Directory for run folders (default `./runs` next to `trials.py`) |
| `TRIALS_RESERVED_SLOTS` | Comma-separated slot IDs never leased (default `3`) |
| `TRIALS_EVPULL` | Script `script <run_dir> <server>` copying the bot event log to `ev-<server>.csv`; omitted skips bot-side events |
| `TRIALS_CORE_DIR` | Core checkout for `build_data.py` (needs `sql/base`) |
| `TRIALS_DEBUG` | Set to `1` to print debug lines (including login pacer logins) |
| `TRIALS_ALLOW_UNPINNED` | Set to `1` to bypass the detached-HEAD / clean-worktree check (tests and emergencies only) |

When `--bind` is passed, the runner also invokes `tbdash-get <server> <api path>` on `PATH` to fetch the dashboard fight list.

Related: [Running, Scoring, and Comparisons](running.md), [Validity Guards](../reliability/validity-guards.md).

[^cli-runner]: Bench CLI entrypoint
[^turtle-agent]: turtle-agent binary and slot lease table
