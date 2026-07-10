# Codex Project Notes

Follow `AGENTS.md` as the primary instruction source.

## Current Direction

DevFlow is V2-only:

```text
Idea -> definition -> spec -> plan -> planning judge -> bounded assignment -> builder/judge -> verification -> next human decision
```

- Hermes owns brainstorming and bounded orchestration.
- DevFlow owns pipeline artifacts and status evidence.
- The browser is a read-only status board, not an agent chat surface.
- Historical UI, task-control, and compatibility surfaces are not in this checkout and must not be recreated without explicit human approval.

## Current Status Board

```bash
source .venv/bin/activate
PYTHONPATH=src .venv/bin/python -m devflow.cli status serve
```

The board serves `http://127.0.0.1:8770/` by default. It provides:

- `/` — status board page;
- `/healthz` — health check;
- `/api/status` — current pipeline runs and events;
- `/api/memory` and `/api/git` — bounded local probes.

## Regression Fixture

```bash
PYTHONPATH=src .venv/bin/python -m devflow.cli loop spine-fixture --json
```

This validates the deterministic V2 stage chain without model calls.

## References

- `AGENTS.md`
- `CODE_MAP.md`
- `docs/DEVFLOW_SOURCE_OF_TRUTH.md`
- `docs/README.md`
- `docs/local-worker-policy.md`
- `docs/verification-ledger.md`
