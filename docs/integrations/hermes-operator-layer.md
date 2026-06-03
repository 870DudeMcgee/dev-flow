# Hermes Operator Layer

Hermes Agent OS is an external operator, chat, scheduling, and delegation layer over Dev-Flow. Hermes may operate Dev-Flow through supervisor-safe commands. Hermes may not become Dev-Flow.

Dev-Flow remains the durable engineering control room and source of truth for:

- task state
- task evidence
- worker isolation
- verification records
- git readiness
- cleanup previews and apply gates
- promotion readiness and promotion

Codex, Qwopus, shell, Antigravity, and other local workers are replaceable execution engines. Josh remains the promotion authority. Hermes memory is convenience context only; Dev-Flow artifacts beat Hermes memory every time.

## Operator Flow

```text
Josh / iPhone / Mac / Hermes CLI / iMessage / gateway
  -> Hermes Agent OS
  -> Dev-Flow supervisor-safe commands
  -> Dev-Flow filesystem/task/evidence state
  -> workers such as Codex, Qwopus, shell, Antigravity
  -> Dev-Flow verification/review/promotion
  -> Josh approves promotion
```

Hermes should prefer JSON surfaces:

```bash
PYTHONPATH=src .venv/bin/python -m devflow.cli status --json
PYTHONPATH=src .venv/bin/python -m devflow.cli dashboard --json
PYTHONPATH=src .venv/bin/python -m devflow.cli supervisor policy --json
PYTHONPATH=src .venv/bin/python -m devflow.cli supervisor packet --json
PYTHONPATH=src .venv/bin/python -m devflow.cli hermes imessage-check --json
PYTHONPATH=src .venv/bin/python -m devflow.cli task next-action <task-id> --json
PYTHONPATH=src .venv/bin/python -m devflow.cli task review <task-id> --json
PYTHONPATH=src .venv/bin/python -m devflow.cli agent list --json
PYTHONPATH=src .venv/bin/python -m devflow.cli agent policy --json
PYTHONPATH=src .venv/bin/python -m devflow.cli agent run --task <task-id> --profile local-qwopus-inspector --dry-run --json
```

## Operating Rules

Hermes defaults to read-only. It may inspect, summarize, recommend next safe actions, prepare Codex prompts, notify a human operator, run scheduled read-only briefs, and capture approved ideas through Dev-Flow commands.

Hermes must not directly edit:

- `.devflow/`
- source files
- the git index
- branches
- remotes
- promotion state

Human approval remains required for task creation, knowledge capture, worker execution, verification runs, cleanup apply, patch application, promotion, merge, push, and broad mutation. Hermes may recommend those actions only after citing Dev-Flow readiness evidence and the exact command for the human to approve.

## Gateway And Mobile Use Cases

Good Hermes use cases:

- answer "what is happening?" from chat or mobile
- summarize review queue and blocked tasks
- prepare short Codex prompts grounded in task evidence
- remind Josh about stale or failed work
- ask for explicit approval before a bounded mutation
- report the next safe action without dumping raw logs

Bad Hermes use cases:

- hidden background schedulers that mutate Dev-Flow
- auto-promotion or auto-push
- using Hermes memory as canonical project state
- direct source edits outside a task workspace/worktree
- unbounded worker spawning
- mixing personal/iMessage automation authority with repo authority

## Scheduled Briefs

Hermes cron jobs are allowed only as read-only status/reporting loops unless Josh explicitly approves a separate mutation command.

### Morning Dev-Flow Brief

- Read-only commands: `status --json`, `supervisor packet --json`, `git status`
- Output: status, review queue, blocked tasks, one next safe action
- Alert-worthy: failed verification, dirty main checkout, stale/conflicted promotion evidence
- Must not: run workers, verify, cleanup, promote, push, or create tasks

### Evening Dev-Flow Debrief

- Read-only commands: `dashboard --json`, `task list`, `supervisor packet --json`
- Output: what changed today, what remains active, what needs Josh
- Alert-worthy: long-running active tasks, failed runs, missing evidence
- Must not: close tasks or promote work automatically

### Stale Task Watchdog

- Read-only commands: `status --json`, `task next-action <task-id> --json`
- Output: stale/blocked list and recommended human-safe next action
- Alert-worthy: stale/conflicted promotion evidence, failed verification, old active tasks
- Must not: repair state, remove locks, or delete worktrees

### Git Hygiene Check

- Read-only commands: `git status`, `worktree list`, `branch list`
- Output: main cleanliness, Dev-Flow worktrees, Dev-Flow branches
- Alert-worthy: dirty main checkout, orphaned worktree candidates, diverged main
- Must not: run `sync-main`, `push-main`, `worktree prune --apply`, or `branch archive` without explicit approval

### Knowledge/Idea Review Queue

- Read-only commands: `knowledge list`, `knowledge search <query>`
- Output: proposed notes that need human review
- Alert-worthy: useful notes stuck in proposed state
- Must not: promote/reject knowledge or create tasks without approval

## Skill And Profile Boundaries

Hermes profiles that can read personal messages or mobile gateways must not inherit mutation authority over Dev-Flow. Keep a dedicated Dev-Flow operator profile with:

- read-only default
- command allowlist
- no secrets in logs
- short status replies for iMessage
- explicit approval language before mutation
- Dev-Flow artifacts as canonical state

## Path Authority

Josh's current canonical local checkout is:

```text
/Users/jewelbait/Desktop/Local AI Dev Team
```

The old local checkout path is quarantined and must not be used for current work:

```text
/Users/jewelbait/Desktop/DevFlow
```

Do not hardcode `DevFlow` as a universal checkout folder. Other operators should use their actual repo root or `<repo-root>`. Do not restore legacy/quarantined material into active authority.

## Non-Goals

This integration does not add a Hermes worker adapter, provider-backed execution, a dashboard server, a database, autonomous routing, hidden memory, or a competing orchestration loop. Future non-shell worker runtime work must follow the registry and adapter sequence documented in the active architecture notes.
