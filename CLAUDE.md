Read `docs/DevFlow_Software_Factory_Vision_Architecture_Blueprint.docx` first —
it is the immutable, highest product/architecture/direction authority for
DevFlow and its Obsidian integration (north-star direction, not necessarily
current runtime state). Then read `AGENTS.md`.

DevFlow is V2-only. For current-implementation detail, read
`docs/DEVFLOW_SOURCE_OF_TRUTH.md` (subordinate to the blueprint) and `CODE_MAP.md`
before changing loop logic, the status board, or documentation.

Use only the current command surface:

```bash
PYTHONPATH=src .venv/bin/python -m devflow.cli status serve
PYTHONPATH=src .venv/bin/python -m devflow.cli loop spine-fixture --json
```

Do not restore retired commands, UI flows, compatibility shims, or historical
architecture unless the human explicitly requests archival recovery. Do not
push or merge without explicit human approval.
