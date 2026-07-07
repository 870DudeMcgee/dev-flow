# DevFlow

DevFlow is a local operating layer for turning rough ideas into verified product implementations.

It is intentionally narrow: DevFlow owns the active product-building loop, while Obsidian owns broad knowledge/context and Git/files own the actual product artifacts.

```text
Idea -> Brainstorm -> Spec -> Plan -> Judge -> Build -> Judge -> Verify -> Next human decision
```

## Current Source of Truth

Start here:

- [docs/DEVFLOW_SOURCE_OF_TRUTH.md](docs/DEVFLOW_SOURCE_OF_TRUTH.md) — active product and architecture direction.
- [docs/README.md](docs/README.md) — active docs index.
- [docs/local-worker-policy.md](docs/local-worker-policy.md) — compact local worker boundary, if kept aligned with the source of truth.
- [docs/verification-ledger.md](docs/verification-ledger.md) — factual evidence history, if kept non-prescriptive.

Older architecture, roadmap, cockpit, orchestration, local-worker, model-routing, DevMode, and software-factory documents are non-authoritative unless explicitly re-approved by the source-of-truth document. Historical material lives under [docs/_quarantine_2026-07-07/](docs/_quarantine_2026-07-07/) for recovery only and must not be loaded as active context by default.

## What DevFlow Is

DevFlow helps a human move from a vague idea to a safe product change:

1. Capture a rough idea.
2. Force it into a clearer product definition.
3. Build an implementation-aware spec from real repo/context constraints.
4. Produce a bounded plan.
5. Judge the plan before execution.
6. Delegate small implementation slices to bounded workers.
7. Judge builder output against evidence.
8. Verify with concrete files, diffs, commands, logs, and tests.
9. Present the next safe human decision.

DevFlow should not become an all-purpose AI command center, second brain, autonomous software factory, model zoo manager, or dashboard that hoards every piece of context.

## Active Boundaries

| Layer | Owns |
|---|---|
| Human | Intent, taste, priority, approvals, final decisions. |
| Obsidian | Broad data, knowledge, notes, long-lived context. |
| DevFlow | Active product-building execution loop. |
| Git/filesystem | Code, docs, diffs, artifacts, source of record. |
| Local workers | Bounded labor with evidence. |
| Hermes | Runtime/tool harness and messaging/orchestration helper. |

DevFlow gathers only the context required to advance the current product-building stage safely.

## Install From This Checkout

```bash
python -m venv .venv
.venv/bin/python -m pip install -e .
```

If the `devflow` console script is unavailable, use the module entrypoint:

```bash
env PYTHONPATH=src:. .venv/bin/python -m devflow.cli --help
```

## Common Commands

### Initialize and inspect

```bash
.venv/bin/python -m devflow.cli init
.venv/bin/python -m devflow.cli doctor
.venv/bin/python -m devflow.cli reconcile
```

### Run the local operating layer UI

```bash
source .venv/bin/activate
devflow operating-layer serve              # http://127.0.0.1:8765/
devflow operating-layer serve --port 0      # print an ephemeral port
devflow operating-layer serve --open        # open the default browser
```

The active browser UI is the `Dev-Flow Operating Layer` surface centered on `Brainstorm`, `Pipeline`, `Worker lanes`, `Review queue`, and `Evidence stream`. If a browser shows an older marketing/control-plane page, treat it as stale and open a cache-busted local URL.

### Capture and promote ideas

```bash
.venv/bin/python -m devflow.cli idea capture "rough idea"
.venv/bin/python -m devflow.cli idea list
.venv/bin/python -m devflow.cli idea show <idea-id>
.venv/bin/python -m devflow.cli idea classify <idea-id>
.venv/bin/python -m devflow.cli idea promote <idea-id> --target goal
.venv/bin/python -m devflow.cli idea create-goal <idea-id> --dry-run
.venv/bin/python -m devflow.cli idea create-goal <idea-id>
```

### Create, run, verify, and inspect a task

```bash
TASK_ID=$(.venv/bin/python -m devflow.cli task create "write hello result" | sed -n 's/^Created \(task-[^:]*\):.*/\1/p')
.venv/bin/python -m devflow.cli task run "$TASK_ID" --worker shell -- /bin/sh -c "echo hello > result.txt"
.venv/bin/python -m devflow.cli task verify "$TASK_ID" --shell "test -f result.txt"
.venv/bin/python -m devflow.cli task show "$TASK_ID"
.venv/bin/python -m devflow.cli task promote-preview "$TASK_ID"
```

Promotion is explicit and human-controlled:

```bash
.venv/bin/python -m devflow.cli task promote "$TASK_ID"
```

Use promotion only after reviewing preview and verification evidence.

### Prefer Git-native lanes for serious work

```bash
TASK_ID=$(.venv/bin/python -m devflow.cli task create --git-worktree "write hello result" | sed -n 's/^Created \(task-[^:]*\):.*/\1/p')
.venv/bin/python -m devflow.cli task run "$TASK_ID" --worker shell -- /bin/sh -c "echo hello > result.txt"
.venv/bin/python -m devflow.cli task verify "$TASK_ID" --shell "test -f result.txt"
.venv/bin/python -m devflow.cli task finalize "$TASK_ID"
.venv/bin/python -m devflow.cli task finalize "$TASK_ID" --commit
.venv/bin/python -m devflow.cli task promote-preview "$TASK_ID"
.venv/bin/python -m devflow.cli task promote "$TASK_ID"
```

Git-native promotion refuses if the worker branch HEAD differs from the verified commit, the worktree is dirty after verification, the baseline is stale without explicit review, or merge conflicts are predicted.

## Safety Model

DevFlow `0.1.0` is an unreleased local MVP for a trusted single-user machine. It is not a security sandbox for untrusted commands, agents, repositories, or multi-user execution.

- Shell and verification commands run as local subprocesses in task workspaces.
- Workers use local user permissions and are path-isolated, not sandboxed.
- Promotion is explicit, readiness-gated, and human-controlled.
- Patch application is text-only and evidence-backed.
- Model output must not auto-apply, auto-verify, auto-promote, commit, merge, or push.

## Runtime State

DevFlow stores local runtime evidence under `.devflow/`:

```text
.devflow/
  ideas/<idea-id>/
  goals/<goal-id>/
  tasks/<task-id>/
  workspaces/<task-id>/
  worktrees/<task-id>/
  reports/
  knowledge/
```

The `.devflow/` tree is generated local state and is intentionally ignored by Git. Seed/template authority lives in `src/devflow/control_room/seed.py`; source authority lives in checked-in code, docs, and tests.

## Development Boundary

Active control-room code belongs under:

```text
src/devflow/control_room/
```

Top-level `src/devflow/*.py` files should stay limited to package/CLI entrypoints and explicit bridges into `src/devflow/control_room/`.

## Verification

Focused verification for this source-of-truth reset:

```bash
.venv/bin/python -m pytest \
  tests/test_packaging.py \
  tests/test_project_scope_docs.py \
  tests/test_devmode_contract.py \
  tests/test_code_map_check.py \
  tests/test_workflow_orchestration_docs.py \
  tests/test_worker_permission_modes.py \
  tests/test_context_pack.py \
  tests/test_estimator.py \
  tests/test_router.py \
  tests/test_scorecard.py \
  -q
```

Broader feature work should run the tests tied to the changed code path before promotion.

## Release And Versioning

- [CHANGELOG.md](CHANGELOG.md) records release notes, semantic versioning rules, and state compatibility requirements.
- The package metadata uses this README as the public long description.
- No public release artifact has been published yet; `0.1.0` is the unreleased local MVP line.

## License

DevFlow is released under the [MIT License](LICENSE).

This repository also contains DevMode skill and harness material influenced by [Superpowers](https://github.com/obra/superpowers). Attribution details are in [ATTRIBUTION.md](ATTRIBUTION.md).
