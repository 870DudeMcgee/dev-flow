# DevFlow Verification Ledger

This ledger records current V2 verification only. Historical UI and runner
claims were removed from the active checkout; recover them from the Git archive
only when a human explicitly asks.

## V2-Only Removal — 2026-07-10

| Check | Result |
|---|---|
| Focused V2 CLI, loop, and status-board suite | Passed — exit `0` |
| Full remaining pytest suite | Passed — exit `0` (two pre-existing Pydantic serialization warnings) |
| Python compilation for active CLI and core loop modules | Passed |
| Ruff on active source and focused V2 tests | Passed |
| V2 CLI import | Passed — no retired namespace module loaded |
| CLI command surface | Passed — only `status` and `loop` exposed |
| Deterministic fixture | Passed — completed the full V2 stage chain |
| Clean wheel build and isolated install | Passed — installed CLI fixture completed; retired payload absent |
| Retired source directory | Absent from the working tree |
| Active stale-command/namespace scan | No matches |

Commands exercised:

```bash
PYTHONPATH=src .venv/bin/python -m pytest \
  tests/test_v2_cli.py tests/test_loop_models.py tests/test_loop_adapter.py \
  tests/test_loop_orient.py tests/test_planning_judge.py \
  tests/test_loop_builder_judge.py tests/test_loop_verification.py \
  tests/test_loop_human_decision.py tests/test_loop_e2e_harness.py \
  tests/test_control_room_git_status.py tests/test_control_room_memory.py -q

PYTHONPATH=src .venv/bin/python -m pytest -q
.venv/bin/ruff check src/devflow tests/test_v2_cli.py
PYTHONPATH=src .venv/bin/python -m devflow.cli loop spine-fixture --json
```
