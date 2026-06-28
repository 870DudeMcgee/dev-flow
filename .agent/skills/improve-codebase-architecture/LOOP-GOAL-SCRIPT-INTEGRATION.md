# Loop-Goal-Script Integration

Loop-Goal-Script is the engine. This skill only prepares goals and evidence.

Local checkout:

```bash
/Users/josh/Desktop/Loop Goal Script/loop.py
```

## Start

Dry-run first:

```bash
python skills/improve-codebase-architecture/scripts/start_rehab_loop.py --repo <repo-root> --candidate "<slice>" --max-iterations 1 --dry-run
python skills/improve-codebase-architecture/scripts/start_rehab_loop.py --repo <repo-root> --candidate "<slice>" --max-iterations 1 --worker codex55 --dry-run
```

Real local-fast start, only when approved:

```bash
python skills/improve-codebase-architecture/scripts/start_rehab_loop.py --repo <repo-root> --candidate "<slice>" --max-iterations 1 --worker local-fast
```

Real Codex 5.5 start, only when approved:

```bash
python skills/improve-codebase-architecture/scripts/start_rehab_loop.py --repo <repo-root> --candidate "<slice>" --max-iterations 1 --worker codex55
```

Worker presets:

- `local-fast` -> Hermes profile `dflocalfast`, model `qwen35-9b-mtp`, local endpoint `127.0.0.1:8080`.
- `codex55` -> Hermes profile `dfcodex55`, model `gpt-5.5`, provider `openai-codex`.

The wrapper passes `--profile` to Loop-Goal-Script and preflights real starts. Do not use Loop-Goal-Script's default `qwen-worker` on this machine unless the operator has explicitly started and verified the matching server.

For rehab goals, the wrapper also passes `--judge-profile dfcodex55` by default, including Codex 5.5 worker runs. Smoke goals stay judge-free by default with `--no-judge` and are bounded with `--session-timeout 120 --hermes-max-turns 2 --hermes-toolsets terminal --hermes-ignore-rules` so lifecycle checks inspect the tiny repo without loading the full agent rules/tool surface.

Use `--background` only when the operator wants the loop to continue outside the current terminal.

## Status And Control

```bash
/Users/josh/Desktop/Loop Goal Script/loop.py status
/Users/josh/Desktop/Loop Goal Script/loop.py watch <slug> --once
/Users/josh/Desktop/Loop Goal Script/loop.py pause <slug>
/Users/josh/Desktop/Loop Goal Script/loop.py resume <slug>
/Users/josh/Desktop/Loop Goal Script/loop.py inject <slug> "Narrow to the scorecard slice; do not touch adjacent files."
/Users/josh/Desktop/Loop Goal Script/loop.py stop <slug>
```

Wrapper status:

```bash
python skills/improve-codebase-architecture/scripts/rehab_loop_status.py --repo <repo-root> --slug <slug>
```

## Ownership Boundaries

Loop-Goal-Script owns:

- iteration
- fresh context
- markdown handoff
- progress detection
- judge behavior
- pause, resume, stop, inject, watch
- task-store sync

This skill owns:

- initial rehab goal text
- Graphify evidence refresh expectations
- before/after scorecards
- Ponytail slice constraints
- subagent prompts and review gates

## Validation Rule

Routine validation must not launch a model. Use `--dry-run` for `start_rehab_loop.py`. Run a real `--max-iterations 1` loop only as an explicit integration smoke after approval.
