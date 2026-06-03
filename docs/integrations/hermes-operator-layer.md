# Hermes Operator Layer

Hermes Agent OS is an external operator, chat, and scheduling layer over Dev-Flow. It is not Dev-Flow's source of truth, runtime, hidden memory layer, or orchestration brain.

Dev-Flow remains authoritative for:

- task state
- task evidence
- worker isolation
- verification records
- git readiness
- cleanup previews and apply gates
- promotion readiness and promotion

Hermes consumes existing supervisor-safe Dev-Flow commands. It should prefer JSON surfaces such as:

```bash
PYTHONPATH=src .venv/bin/python -m devflow.cli status --json
PYTHONPATH=src .venv/bin/python -m devflow.cli dashboard --json
PYTHONPATH=src .venv/bin/python -m devflow.cli supervisor policy --json
PYTHONPATH=src .venv/bin/python -m devflow.cli supervisor packet --json
PYTHONPATH=src .venv/bin/python -m devflow.cli task next-action <task-id> --json
PYTHONPATH=src .venv/bin/python -m devflow.cli task review <task-id> --json
```

## Operating Rules

Hermes defaults to read-only. It may inspect, summarize, recommend next actions, packetize evidence for a human, notify an operator, and capture approved ideas through Dev-Flow commands.

Hermes must not directly edit:

- `.devflow/`
- source files
- the git index
- branches
- remotes
- promotion state

Hermes must not treat its own memory as canonical Dev-Flow state. Dev-Flow artifacts beat Hermes memory every time.

Human approval remains required for promotion, merge, push, cleanup apply, direct task mutation, worker execution, verification runs, and broad mutation. Hermes may recommend those actions only after citing Dev-Flow readiness evidence and the exact command for the human to run.

## Path Authority

Josh's current canonical local checkout is:

```text
/Users/jewelbait/Desktop/Local AI Dev Team
```

The old local checkout path is quarantined and must not be used for current work:

```text
/Users/jewelbait/Desktop/DevFlow
```

Do not hardcode `DevFlow` as a universal checkout folder. Other operators should use their actual repo root.

## Non-Goals

This integration does not add a Hermes worker adapter, direct provider runtime, autonomous scheduler, hidden state store, vector memory, or competing orchestration loop. Future non-shell worker runtime work must follow the registry and adapter sequence documented in the active architecture notes.
