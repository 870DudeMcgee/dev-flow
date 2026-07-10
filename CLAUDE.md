Read `AGENTS.md` first.

DevFlow is V2-only. Read `docs/DEVFLOW_SOURCE_OF_TRUTH.md` and `CODE_MAP.md`
before changing loop logic, the status board, or documentation.

Use only the current command surface:

```bash
PYTHONPATH=src .venv/bin/python -m devflow.cli status serve
PYTHONPATH=src .venv/bin/python -m devflow.cli loop spine-fixture --json
```

Do not restore retired commands, UI flows, compatibility shims, or historical
architecture unless the human explicitly requests archival recovery. Do not
push or merge without explicit human approval.
