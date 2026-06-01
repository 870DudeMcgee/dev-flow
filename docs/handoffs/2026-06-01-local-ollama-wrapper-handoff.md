# Handoff: Local Ollama Worker Wrapper

## Status

complete

## Files Changed

- AGENTS.md: clarified that `devflow task local` is a narrow local Ollama evidence wrapper, not a code-changing adapter path.
- README.md: documented the `task local` commands, artifact layout, safety boundary, and future Ollama resource-control work.
- docs/agent-handoff.md: added the legacy local Qwen/Qwopus/Gemma advisory command and artifact contract for future agents.
- docs/control-room-mvp.md: aligned the MVP source of truth with the local Ollama evidence wrapper and its non-goals.
- docs/mvp-contract.md: added `devflow task local` to the stable command contract and described local-worker artifacts.
- docs/roadmap.md: recorded the first local Ollama wrapper as implemented while keeping promoted provider adapters deferred.
- src/devflow/cli.py: added `devflow task local <task_id> --worker <name> [--input-worker <name>] [--timeout-seconds N]`.
- src/devflow/control_room/service.py: added task-local service orchestration with locks, `task.yaml` updates, and hash-chained local-worker events.
- src/devflow/control_room/local_ollama_worker.py: added Qwen/Qwopus/Gemma advisory worker definitions, prompt composition, `ollama run` subprocess execution, timeout handling, artifact writing, and run metadata.
- tests/test_local_ollama_worker.py: added mocked subprocess coverage for prompt composition, artifact writes, reviewer input, missing input failure, nonzero exit, timeout, unknown worker, and exit-code-based success.

## Verification

- `PYTHONPATH=src ./.venv-local/bin/python3 -m pytest tests/test_local_ollama_worker.py -q`: failed because `.venv-local` does not have pytest installed.
- `PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_local_ollama_worker.py -q`: pass, `8 passed`.
- `PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_local_ollama_worker.py tests/test_control_room_shell.py tests/test_cli.py tests/test_ollama_worker.py tests/test_manual_proof_agent.py tests/test_mvp_boundaries.py -q`: pass, `53 passed, 1 skipped`.
- `PYTHONPATH=src ./.venv/bin/python -m pytest -q`: pass, `385 passed, 6 skipped`.

## Risks

- Local worker artifacts live under `.devflow/workspaces/<task_id>/local-workers/<worker-name>/`; future promotion UX may need to classify or ignore these evidence files explicitly.
- The wrapper does not manage Ollama memory, keep-alive, or model-stop behavior.
- The wrapper does not parse or trust model output, auto-edit repo files, verify, commit, merge, promote, route models, or call remote provider APIs.
- Pre-existing dirty `.devflow/context/active/README.md`, `.devflow/project/project.yaml`, and `.DS_Store` files were not part of this slice and should not be accidentally committed.

## Next Safe Action

- Dogfood the new commands against a real local Ollama task, inspect `run.json` and `response.raw.md`, then decide whether promotion preview should hide or classify `local-workers/` evidence files before any workflow relies on promotion from the same workspace.
