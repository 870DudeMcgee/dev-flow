# Control-Room Refactoring Integration

Status: current integration note for goal `G-0001` / slice `TS-0005`.

## Purpose

Goal `G-0001` deepened four active control-room modules without changing the product boundary. The integrated runtime still keeps Dev-Flow responsible for task state, patch gates, worker evidence, status visibility, verification, and human-controlled promotion.

This note records the selected lanes and the final module interfaces after integration:

- `TS-0002`: patch evidence ladder
- `TS-0003`: executable worker runtime versus planned adapters
- `TS-0004`: status, dashboard, and review capsule projection
- `TS-0001`: task lifecycle state mutation

No selected lane enables remote provider execution, autonomous routing, direct main checkout mutation, or automatic promotion.

## Integrated Module Interfaces

### Patch Proposals

`src/devflow/control_room/patch_proposal.py` is the shared patch proposal module. Patch review, dry-run, and apply code delegate parsing, touched-file extraction, path-risk checks, and workspace target resolution to this module.

Primary callers:

- `patch_review.py`
- `patch_dry_run.py`
- `patch_applier.py`

The patch proposal module is evidence-oriented. It does not apply patches, run verification, stage files, commit, or promote.

### Provider Patch Worker Evidence

`src/devflow/control_room/provider_patch_worker.py` centralizes provider-style patch evidence behavior for provider worker adapters. It writes task-local proposal evidence and failure evidence through one adapter helper.

Primary callers:

- `openai_compatible_worker.py`
- `openai_chat_worker.py`
- `anthropic_worker.py`
- `gemini_worker.py`

The normal worker lookup still rejects experimental read-only provider adapters. Provider adapter code existing behind this helper does not make remote providers part of the stable executable runtime.

### Status Projection

`src/devflow/control_room/status_projection.py` is the shared read model for task status, verification display, merge readiness, manual-agent states, dashboard next actions, and review capsule decision text.

Primary callers:

- `dashboard.py`
- `review_capsule.py`
- `task_packet.py`
- CLI task list/show rendering through the existing control-room service path

The projection module reads canonical artifacts and derived readiness evidence. It must remain read-only and cannot replace `task.yaml`, `events.jsonl`, or `verification.json`.

### Task Workbench Projection

`src/devflow/control_room/task_workbench.py` is the read-only task-centered projection for the operating-layer workbench. It composes task lanes, focus task, review queue items, evidence pointers, task-progress receipts, worker activity rows, worker/model labels, and intent-labeled task controls from existing filesystem-backed projections.

Primary caller:

- `operating_layer.py`

The workbench projection adapts status, review-readiness, git-worktree, local-worker-lane, and agent-evidence modules. It does not spawn workers, verify tasks, promote tasks, mutate canonical artifacts, or widen browser command authority.

### Task Lifecycle

`src/devflow/control_room/task_lifecycle.py` is the write facade for task status updates, lifecycle events, summary writes, merge-readiness writes, and verification invalidation after workspace mutation.

Primary callers:

- `service.py`
- `promotion.py`
- `task_closure.py`

`persistence.py` remains the low-level artifact writer. Lifecycle transitions should go through `task_lifecycle.py` so callers do not duplicate artifact ordering or readiness rules.

## Integration Result

The four selected branches merged cleanly into `devflow/task-0053/shell`:

- `devflow/task-0049/shell`
- `devflow/task-0050/shell`
- `devflow/task-0051/shell`
- `devflow/task-0052/shell`

Shared-file conflict risk was highest around task state, projection display, and worker adapter maturity. The selected lanes changed disjoint active files except for ordinary cross-module imports, so no textual conflicts were required during integration.

## Verification Contract

Before this integration branch can be considered review-ready:

- selected focused lane tests must pass together
- broad MVP and boundary tests must pass
- `devflow doctor --strict` must pass
- `devflow git status` must remain clean
- promotion remains blocked until explicit human approval
