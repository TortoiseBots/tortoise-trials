---
type: Playbook
title: Running, Scoring, and Comparisons
description: CLI subcommands, parallel arena locks, pinned worktrees, verdicts, and before/after PR blocks.
tags: [cli, run, score, compare, pr-block, worktree]
status: stable
generated: { by: "antigravity/gemini", at: "2026-11-25T14:35:00Z" }
sources:
  - id: cli-sh
    resource: trials.sh (CLI wrapper)
    title: Bench CLI wrapper
  - id: cli-py
    resource: trials.py (run, score, cleanup, compare, pr-block)
    title: Bench CLI implementation
---

# CLI Commands

```bash
./trials.sh list [--class priest]
./trials.sh validate [files...]                      # offline trial validation
./trials.sh run --server S --trial ID --label before [--repeats N] [--parallel 2] [--dry-run]
./trials.sh score <run-dir>                          # re-score a finished run
./trials.sh cleanup <run-dir>                        # remove hires/summons, log out, release leases
./trials.sh compare <run-dir> --baseline <run-dir>
./trials.sh pr-block --before <run-dir> --after <run-dir> [--issue N]
```

- **Selection:** `--trial` is repeatable. `--class` and `--spec` filter by trial metadata. `--trial ID@VARIANT` runs one variant and `--trial 'ID@*'` runs all variants; bare IDs, globs without `@`, and `--class` select base trials only (see [Variants and Player Gear](../trials/variants-and-gear.md)).
- **Parallelism:** `--parallel N` is safe up to `arenas - 1` (4 arenas -> 3). Each worker leases its own slot and holds an exclusive per-arena lock file for the entire repeat so two slots never share an arena.[^cli-py]
- **Cleanup:** `cleanup` is idempotent and reads the run ledger to remove leftover hires/summons. Always run `cleanup` on an aborted run before starting the next one.

# Run Artifacts, Verdicts, and Exit Codes

Each run folder contains `RUN.json` (including `bench_sha`, `bench_detached`, `bench_dirty`), per-trial/repeat folders with raw samples, `events.jsonl`, `setup.json`, `verdicts.json`, and `card.md` / `card.json`.

- **Verdicts:** `PASS`, `FAIL`, `INCONCLUSIVE` (insufficient opportunity or data), or `INVALID` (a validity guard failed; see [Validity Guards](../reliability/validity-guards.md)).
- **Exit codes:** `0` ok, `1` problems, `4` safety refusal, `5` server/RPC error or leftover summon.

# Pinned Worktree Requirement

`trials run` refuses to start (exit `4`, before any server contact; `--dry-run` excepted) unless the checkout has a **detached HEAD** and **no modified tracked files** (`git status --porcelain --untracked-files=no` is empty).[^cli-py]

```bash
sha=$(git -C ~/bench-wt rev-parse HEAD)
git -C ~/bench worktree add --detach ~/bench-run-${sha:0:7} $sha
cd ~/bench-run-${sha:0:7} && . ~/bench/local/trials.env
./trials.sh run --server <test-server> --trial ... --repeats 4 --parallel 1 --label bench-fix-1111
```

Setting `TRIALS_ALLOW_UNPINNED=1` overrides this for tests/emergencies and stamps `"bench_unpinned": true` in `RUN.json`.

# Before and After PR Blocks

Run the same trials against the baseline build (`--label before`) and the candidate build (`--label after`), then generate a PR summary block:

```bash
./trials.sh pr-block --before runs/<before> --after runs/<after> --issue 1553
```

The output includes a before/after verdict table, cited bot source lines and event evidence, and setup proofs. Statistical differences use **Fisher's exact test** on the summed `k/n` across valid repeats (`compare` annotates p-values as `"differs (p<0.05)"`, `"suggestive (p<0.20)"`, or `"no evidence"`).

# Examples

**TortoiseBots #1553 / PR #1557:** A Holy priest shielded a Defensive Stance Arms warrior when a second tank was present. Trials `priest-holy-pws-def-arms-2tank` and `priest-holy-pws-def-arms-ooc` reproduced it:

- Two tanks in combat: Power Word: Shield above critical band dropped from `16` before to `0` after.
- Between pulls: `18` before to `0` after.
- Controls (Battle Stance warrior and warrior-as-bot): remained shielded as expected.

Related: [Configuration and Environment](configuration.md), [Trial File Format](../trials/format.md).

[^cli-sh]: Bench CLI wrapper
[^cli-py]: Bench CLI implementation
