# Evidence Review Detail Adapter Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` or `executing-plans` to implement this plan task-by-task. Track progress with the checkbox steps below.

Date: 2026-06-26
Status: ready for implementation handoff

## Goal

Finish the next operating-layer cleanup slice by making `EvidenceReviewDetail` the shared Interface for the operator-facing evidence and review story, including supervisor review output.

After this slice:

- `src/devflow/control_room/evidence_review_detail.py` owns the evidence paths, changed-file story, worker/model evidence summary, review readiness, promotion blockers, and operator-facing artifacts for a task.
- `task_workbench.py` keeps consuming `EvidenceReviewDetail` as it does today.
- `supervisor_surface.py` uses `EvidenceReviewDetail` for operator-facing review JSON/text fields instead of maintaining a separate evidence path and changed-file story.
- Supervisor policy decisions still use the existing approval classes, patch review/dry-run status checks, and next-action guardrails.
- Existing supervisor JSON keys remain compatible; new detail fields may be added, but do not remove or rename current keys in this slice.

## Current State

Start from clean `main` after commit:

```text
a013161 refactor: prefer first viewport presentation
```

Current architecture state:

- Candidate 1 is complete: `task_workbench.py` owns task-centered projection and `operating_layer.py` is a thinner Adapter.
- Candidate 2 is complete: `browser_task_capabilities.py` owns task command capabilities and project scoping.
- Candidate 3 is complete: `operating_layer_first_viewport.py` owns the current first-viewport presentation Interface and JavaScript is the DOM Adapter/fallback.
- Candidate 4 is partially built: `evidence_review_detail.py` exists and is used by `task_workbench.py`, but `supervisor_surface.py` still builds a parallel `_task_evidence()` dictionary with its own evidence paths, changed files, patch artifact paths, missing evidence, and review text inputs.

The next cleanup is an Adapter-thinning slice, not a new Module. The goal is to deepen the existing evidence/review Module and have the supervisor consume it for operator-facing meaning while preserving supervisor-specific policy mechanics.

## Non-Goals

- Do not redesign the browser UI.
- Do not change browser action approval policy or supervisor safety classes.
- Do not remove compatibility keys from `devflow task review --json`.
- Do not remove `review_readiness.py`; it remains the readiness classifier feeding `EvidenceReviewDetail`.
- Do not remove patch review, patch dry-run, promotion preview, or git fact readers if supervisor policy still needs their raw payloads.
- Do not use Hyperplane for validation.
- Do not push, publish, promote, or open a PR.
- Do not commit `graphify-out/`.

## Files Likely To Modify

- `src/devflow/control_room/evidence_review_detail.py`
- `src/devflow/control_room/supervisor_surface.py`
- `tests/test_evidence_review_detail.py` or focused additions near existing evidence tests
- `tests/test_supervisor_operating_surface.py`
- `tests/test_task_workbench_projection.py`
- `tests/test_operating_layer.py`
- `docs/architecture/operating-layer-ui-deepening-backlog.md`
- optionally `docs/architecture/control-room-cleanup-checkpoint-2026-06-25.md`

## Task 0: Confirm Baseline

- [ ] Run:

```bash
git status --short
PYTHONPATH=src:. .venv/bin/python -m devflow.cli git status
```

Expected:

- clean working tree
- local `main` may be ahead of `origin/main`
- `safe_for_worker_writes: yes`

- [ ] Run focused baseline tests:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest \
  tests/test_task_workbench_projection.py \
  tests/test_operating_layer.py::test_operating_layer_snapshot_includes_compact_agent_evidence_summary \
  tests/test_supervisor_operating_surface.py::test_task_review_json_cites_evidence_paths_and_tolerates_missing_artifacts \
  -q
```

Expected: pass before changes.

## Task 1: Add Direct Evidence Detail Coverage

Files:

- Add or modify: `tests/test_evidence_review_detail.py`
- Optionally modify: `tests/test_task_workbench_projection.py`

- [ ] Add a direct test for `build_evidence_review_detail()` using a task with:
  - task metadata and events
  - worker log and result evidence
  - local/model or patch-agent evidence
  - patch proposal evidence
  - patch review or patch dry-run evidence
  - missing verification evidence tolerated

Required assertions:

- `detail.schema_version == 1`
- `detail.task_id` and `detail.title` match the task
- `detail.evidence_paths` includes `.devflow/tasks/<task_id>/task.yaml`
- `detail.evidence_paths` includes `.devflow/tasks/<task_id>/events.jsonl`
- `detail.evidence_paths` includes patch proposal evidence when present
- `detail.evidence_paths` includes patch review or patch dry-run evidence when present
- missing optional artifacts are captured in `detail.missing_evidence`
- `detail.changed_files` includes files reported by patch review, patch dry-run, or promotion preview evidence, not only files already changed in a workspace
- `detail.artifacts` includes concrete artifact entries for worker result, patch proposal, model/agent evidence, and any patch review/dry-run evidence that exists
- `detail.operator_summary` remains a short operator-facing sentence

- [ ] Add or keep a Task workbench assertion that `task.review_detail.evidence_paths == task.evidence_paths`.

Run:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_evidence_review_detail.py tests/test_task_workbench_projection.py -q
```

Expected before implementation: the new direct test may fail because `EvidenceReviewDetail` does not yet own every path/file source.

## Task 2: Deepen `evidence_review_detail.py`

Files:

- Modify: `src/devflow/control_room/evidence_review_detail.py`

- [ ] Extend `EvidenceReviewDetail` with these additive fields for current operator-facing evidence:
  - `missing_evidence: list[str]`
  - `proposal_patch_paths: list[str]`
  - `patch_review_path: str | None`
  - `patch_dry_run_path: str | None`
  - `patch_application_path: str | None`
  - `promotion_preview_path: str | None`
  - `git_facts_path: str | None`
- [ ] Include task metadata evidence (`task.yaml`) and events evidence (`events.jsonl`) in `evidence_paths`.
- [ ] Pull patch proposal paths into the detail from the existing local patch-agent/Qwopus evidence sources.
- [ ] Pull patch review, patch dry-run, patch application, promotion preview, and git facts paths into the detail when those artifacts exist.
- [ ] Merge changed files from these sources, preserving deterministic order:
  - promotion preview `changed_files`, `added`, `modified`, `deleted`, `untracked`, `binary`, and `renamed`
  - patch review `files_touched`
  - patch dry-run `files_checked`, `files_would_create`, `files_would_modify`, and `files_would_delete`
  - workspace changed-file scan already present in `evidence_review_detail.py`
- [ ] Keep `changed_file_preview` best-effort and workspace-based; do not fabricate file contents from patch metadata.
- [ ] Add artifact entries for patch review and patch dry-run when those paths exist.
- [ ] Keep path rendering repo-relative through existing `relative_path()`/display helpers. Do not emit absolute local checkout paths into public JSON unless an existing field already does.

Implementation constraints:

- Avoid importing `supervisor_surface.py` from `evidence_review_detail.py`; that would create the wrong dependency direction.
- It is acceptable to move small helper logic from `supervisor_surface.py` into `evidence_review_detail.py` when the helper is operator-facing evidence assembly.
- Keep policy-specific decisions, approval classes, and command classification in `supervisor_surface.py`.

Run:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_evidence_review_detail.py tests/test_task_workbench_projection.py -q
```

Expected: pass.

## Task 3: Adapt Supervisor Review To The Shared Detail

Files:

- Modify: `src/devflow/control_room/supervisor_surface.py`
- Modify: `tests/test_supervisor_operating_surface.py`

- [ ] Import `build_evidence_review_detail()` and use it when building task review and next-action evidence.
- [ ] Keep `_task_evidence()` or split it into `_task_policy_evidence()` if that keeps the change small, but stop using it as the independent owner of operator-facing evidence paths and changed files.
- [ ] Feed `EvidenceReviewDetail.evidence_paths` into:
  - `build_task_review(... )["evidence_paths"]`
  - `build_task_next_action(... )["evidence_considered"]`
  - compact supervisor packet task records when `include_evidence_paths=True`
- [ ] Feed `EvidenceReviewDetail.changed_files` into `build_task_review(... )["changed_files"]`.
- [ ] Add an `evidence_detail` object to `devflow task review --json` with at least:
  - `review_state`
  - `review_reason`
  - `operator_summary`
  - `artifacts`
  - `changed_file_preview`
  - `agent_evidence_summary`
  - `notes`
- [ ] Preserve existing top-level review keys:
  - `patch_proposal`
  - `patch_review`
  - `patch_dry_run`
  - `patch_application`
  - `verification`
  - `promotion_preview`
  - `git`
  - `risks`
  - `blocked_reasons`
  - `next_action`
  - `commands_safe_to_run`
  - `commands_requiring_human_approval`
  - `evidence_paths`
  - `missing_optional_artifacts`
- [ ] Update `test_task_review_json_cites_evidence_paths_and_tolerates_missing_artifacts` to assert the new `evidence_detail` data and the old compatibility keys together.
- [ ] Add a regression assertion that a file reported only by patch review or dry-run appears in top-level `changed_files` and in `evidence_detail` meaning.

Run:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_supervisor_operating_surface.py::test_task_review_json_cites_evidence_paths_and_tolerates_missing_artifacts -q
```

Expected: pass.

## Task 4: Thin Duplicate Evidence Assembly

Files:

- Modify: `src/devflow/control_room/supervisor_surface.py`
- Modify: `src/devflow/control_room/evidence_review_detail.py` if helper moves are still pending

- [ ] Remove or retire supervisor-local helper code that now belongs to `evidence_review_detail.py`, especially independent evidence path and changed-file aggregation.
- [ ] Keep supervisor-local helpers that are clearly policy mechanics, such as status interpretation and approval risk decisions.
- [ ] Run:

```bash
rg -n "evidence_paths\\.append|evidence_paths\\.extend|missing_evidence|def _proposal_patch_paths|def _changed_files|def _record_path|def _optional_path|def _latest_evidence_path" src/devflow/control_room/supervisor_surface.py
```

Expected:

- no independent operator-facing evidence path aggregation remains in `supervisor_surface.py`
- any remaining matches are policy-specific and documented in the implementation handoff

- [ ] Run:

```bash
rg -n "build_evidence_review_detail|EvidenceReviewDetail" src/devflow/control_room/supervisor_surface.py src/devflow/control_room/task_workbench.py src/devflow/control_room/operating_layer.py
```

Expected:

- `task_workbench.py` and `supervisor_surface.py` both consume the shared detail Module
- `operating_layer.py` should only adapt already-built detail fields, not rebuild evidence meaning

## Task 5: Preserve Operating Layer Behavior

Files:

- Modify: `tests/test_operating_layer.py` only if new fields require fixture alignment
- Modify: `tests/test_task_workbench_projection.py` only if direct assertions need alignment

- [ ] Run:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest \
  tests/test_task_workbench_projection.py \
  tests/test_operating_layer.py::test_operating_layer_snapshot_includes_compact_agent_evidence_summary \
  tests/test_operating_layer.py::test_operating_layer_snapshot_json_is_read_only_contract \
  tests/test_operating_layer.py::test_operating_layer_task_cards_expose_state_specific_next_actions \
  -q
```

Expected: pass.

- [ ] If operating-layer snapshots gain new `review_detail` fields, keep them additive and JSON-serializable through Pydantic `model_dump(mode="json")`.

## Task 6: Update Architecture Notes

Files:

- Modify: `docs/architecture/operating-layer-ui-deepening-backlog.md`
- Optional modify: `docs/architecture/control-room-cleanup-checkpoint-2026-06-25.md`

- [ ] Add a dated Candidate 4 checkpoint saying `EvidenceReviewDetail` is now the shared operator-facing evidence/review Interface for Task workbench and Supervisor review output.
- [ ] Mention that supervisor policy mechanics remain in `supervisor_surface.py` as the approval Adapter.
- [ ] If Graphify is refreshed, record only lightweight metrics in the cleanup checkpoint doc.
- [ ] Do not commit generated `graphify-out/` files.

## Task 7: Verification

Minimum verification:

```bash
git diff --check
PYTHONPATH=src:. .venv/bin/python -m pytest \
  tests/test_evidence_review_detail.py \
  tests/test_task_workbench_projection.py \
  tests/test_operating_layer.py::test_operating_layer_snapshot_includes_compact_agent_evidence_summary \
  tests/test_operating_layer.py::test_operating_layer_snapshot_json_is_read_only_contract \
  tests/test_supervisor_operating_surface.py::test_task_review_json_cites_evidence_paths_and_tolerates_missing_artifacts \
  -q
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_supervisor_operating_surface.py -q
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_architecture_boundaries.py tests/test_code_map_check.py tests/test_mvp_boundaries.py tests/test_project_scope_docs.py -q
PYTHONPATH=src:. .venv/bin/python -m devflow.cli map check
PYTHONPATH=src:. .venv/bin/python -m devflow.cli git status
```

Graphify verification:

```bash
.venv/bin/graphify update .
.venv/bin/graphify diagnose multigraph --json --graph graphify-out/graph.json
.venv/bin/graphify explain "control_room_evidence_review_detail" --graph graphify-out/graph.json
.venv/bin/graphify explain "control_room_supervisor_surface" --graph graphify-out/graph.json
.venv/bin/graphify explain "control_room_task_workbench" --graph graphify-out/graph.json
```

Expected:

- tests pass
- no `graphify-out/` files are committed
- Graphify explains show evidence/review meaning has moved toward `control_room_evidence_review_detail`; `control_room_supervisor_surface` may remain broad because it still owns policy and CLI surface area

## Rollback And Risk Notes

- Main compatibility risk: `devflow task review --json` consumers may depend on existing top-level keys. Keep those keys stable and add `evidence_detail` instead of reshaping the whole payload.
- Main behavior risk: `EvidenceReviewDetail.changed_files` currently scans workspace state, while supervisor changed files can come from patch metadata. Merge both sources rather than choosing one.
- Main architecture risk: moving too much supervisor policy into `evidence_review_detail.py`. Keep command safety, approval classes, and next-action decisions in `supervisor_surface.py`.
- Rollback path: revert the supervisor adapter changes first. `task_workbench.py` already consumes `EvidenceReviewDetail`, so the evidence detail improvements can remain useful even if supervisor adoption needs a follow-up.
