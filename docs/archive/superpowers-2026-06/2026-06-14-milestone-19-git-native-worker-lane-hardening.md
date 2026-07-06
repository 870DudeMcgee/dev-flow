# Milestone 19 Git-Native Worker Lane Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden the opt-in Git-native worker lane so operators can inspect, verify, preview, promote, and clean up Git worktree tasks with consistent evidence across CLI, supervisor, and browser surfaces.

**Architecture:** Add a read-only worker lane summary derived from existing `.devflow/tasks/<task_id>/workers/<worker_id>/` Git evidence, promotion preview evidence, verification evidence, and live read-only Git state. Surface that same projection in task show/review-ready, supervisor status/packet, operating-layer JSON/UI, and dogfood checks. Keep all code-changing runtime behavior on shell workers only.

**Tech Stack:** Python, Typer CLI, Pydantic operating-layer models, pytest, existing Dev-Flow Git worktree helpers in `src/devflow/control_room/`.

---

## Product Constraints

- Keep all active code changes under `src/devflow/control_room/` and existing CLI/tests/docs boundaries.
- Do not implement provider adapters, autonomous routing, automatic promotion, automatic push, pull requests, conflict resolver workers, or Git-native default mode.
- Do not write new feature code under `src/devflow/_legacy/` or revive archived workflows.
- Browser operating-layer changes are read-only except the already-approved exact verification and promotion flows.
- Lane summary reads may run Git inspection commands, but they must not mutate refs, worktrees, task evidence, or promotion evidence.

## References

- `PRODUCT_NORTH_STAR.md`
- `docs/control-room-mvp.md`
- `docs/token-optimization.md`
- `docs/architecture/git-native-worker-isolation-and-promotion.md`
- `docs/architecture/local-operating-layer-ui.md`
- `docs/superpowers/specs/2026-06-14-milestone-19-git-native-worker-lane-hardening-design.md`
- `src/devflow/control_room/git_worktree.py`
- `src/devflow/control_room/operating_layer.py`
- `src/devflow/control_room/supervisor_surface.py`
- `src/devflow/control_room/review_readiness.py`
- `src/devflow/cli.py`
- `tests/test_git_worktree_promotion.py`
- `tests/test_task_finalize.py`
- `tests/test_operating_layer.py`
- `tests/test_supervisor_operating_surface.py`

## Setup

- [ ] Confirm a clean writer checkout.

```bash
PYTHONPATH=src:. .venv/bin/devflow git status
```

- [ ] Start implementation in an isolated worktree or approved single-writer branch.
- [ ] Re-read the references above before editing code.
- [ ] Keep a running handoff note using `docs/handoff-template.md`.

## Task 1: Add Read-Only Worker Lane Summary Tests

Write the tests first.

- [ ] In `tests/test_git_worktree_promotion.py`, add `test_git_worker_lane_summary_reports_ready_and_stale_states`.
- [ ] Import the new helper from `devflow.control_room.git_worktree`:

```python
from devflow.control_room.git_worktree import git_worker_lane_summary
from devflow.control_room.persistence import get_task
```

- [ ] Use the existing `_init_git_repo()`, `_git()`, and `runner` helpers.
- [ ] The test should:
  - create a Git-native task with `runner.invoke(app, ["task", "create", "--git-worktree", "lane summary"])`;
  - commit `ready.txt` inside `.devflow/worktrees/task-0001/shell`;
  - verify the task with `devflow task verify`;
  - run `devflow task promote-preview task-0001`;
  - call `git_worker_lane_summary(Path.cwd(), get_task(Path.cwd(), "task-0001"))`;
  - assert `workspace_mode == "git-worktree"`;
  - assert `worker_id == "shell"`;
  - assert `worker_branch == "devflow/task-0001/shell"`;
  - assert `worktree_path == ".devflow/worktrees/task-0001/shell"`;
  - assert `head_commit == worker_head`;
  - assert `verified_commit == worker_head`;
  - assert `head_matches_verified is True`;
  - assert `dirty is False`;
  - assert `promotion_readiness == "ready"`;
  - assert `conflict_prediction == "clean"`;
  - assert `readiness_status == "ready"`;
  - assert `next_safe_action == "devflow task promote task-0001"`.
- [ ] Advance `main` after the preview with a second commit in the main checkout.
- [ ] Call the summary again and assert:
  - `base_stale is True`;
  - `readiness_status in {"stale", "blocked"}`;
  - `next_safe_action == "devflow task promote-preview task-0001"`.
- [ ] Run the new test and confirm it fails because the helper does not exist yet.

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_git_worktree_promotion.py -k lane_summary -q
```

## Task 2: Implement `git_worker_lane_summary`

- [ ] Add the helper in `src/devflow/control_room/git_worktree.py`.
- [ ] Keep it read-only: do not call `refresh_git_worker_evidence()` or `build_git_promotion_preview()` from the summary helper.
- [ ] Return `None` for non-Git-worktree tasks.
- [ ] Read existing evidence from:
  - `task_worker_dir(root, task.id, worker_id) / "git.json"`;
  - `task_worker_dir(root, task.id, worker_id) / "promotion-preview.json"`;
  - `task_dir(root, task.id) / "verification.json"`.
- [ ] Use existing Git helpers in the same module where possible, such as `_git_output()`, `branch_head()`, `main_head()`, `origin_main_head()`, `_worktree_dirty()`, and `relative_path()`.
- [ ] Normalize absent or invalid evidence into summary fields instead of raising for normal missing-artifact cases.
- [ ] Return at least these keys:

```python
{
    "schema": 1,
    "task_id": task.id,
    "worker_id": worker_id,
    "workspace_mode": "git-worktree",
    "worktree_path": "...",
    "worker_branch": "...",
    "base_branch": "main",
    "base_commit": "...",
    "base_current_commit": "...",
    "base_stale": False,
    "origin_base_commit": "...",
    "origin_base_stale": False,
    "head_commit": "...",
    "dirty": False,
    "verification_status": "passed",
    "verified_commit": "...",
    "head_matches_verified": True,
    "promotion_readiness": "ready",
    "conflict_prediction": "clean",
    "changed_files": ["ready.txt"],
    "readiness_status": "ready",
    "readiness_errors": [],
    "readiness_warnings": [],
    "evidence_paths": [".../git.json", ".../promotion-preview.json", ".../verification.json"],
    "next_safe_action": "devflow task promote task-0001",
}
```

- [ ] Derive `readiness_status` using this precedence:
  - `missing` when expected branch, worktree, or base commit is absent;
  - `dirty` when the worktree has uncommitted changes;
  - `unverified` when verification is missing, failed, or `verified_commit` is absent;
  - `dirty` when `head_commit != verified_commit`;
  - `conflict` when promotion preview reports a non-clean conflict prediction;
  - `stale` when `base_stale` or `origin_base_stale` is true;
  - `ready` when promotion preview readiness is ready and no blockers remain;
  - `blocked` as the fallback for multiple or unknown blockers.
- [ ] Derive `next_safe_action` deterministically:
  - missing evidence: `devflow task show <task_id>`;
  - dirty or head changed after verification: `devflow task verify <task_id> --shell "<command>"`;
  - unverified: `devflow task verify <task_id> --shell "<command>"`;
  - conflict or stale: `devflow task promote-preview <task_id>`;
  - ready: `devflow task promote <task_id>`.
- [ ] Re-run the focused lane summary test until it passes.

## Task 3: Surface Lane Summary in CLI and Review Readiness

Write tests first.

- [ ] In `tests/test_git_worktree_promotion.py`, extend an existing Git-native task test or add `test_task_show_and_review_ready_include_worker_lane_summary`.
- [ ] Assert `devflow task show task-0001` includes:
  - `worker_lane: git-worktree`;
  - `worker_branch: devflow/task-0001/shell`;
  - `worktree_path: .devflow/worktrees/task-0001/shell`;
  - `lane_readiness: ready`;
  - `lane_next_action: devflow task promote task-0001`.
- [ ] Assert `devflow task review-ready task-0001` includes:
  - `worker_lane: git-worktree`;
  - `lane_readiness: ready`.
- [ ] Update `src/devflow/cli.py`:
  - import `git_worker_lane_summary`;
  - print a compact lane block in `task_show`;
  - include lane readiness in the `task_review_ready` renderer without changing JSON schema incompatibly.
- [ ] Update `src/devflow/control_room/review_readiness.py` only if the renderer needs the projection to carry lane fields. Prefer optional fields with defaults so non-Git tasks keep their current output.
- [ ] Re-run:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_git_worktree_promotion.py tests/test_task_finalize.py -q
```

## Task 4: Surface Lane Summary in Supervisor Status and Packet

Write tests first.

- [ ] In `tests/test_supervisor_operating_surface.py`, extend `test_git_native_promotion_ready_task_is_reported_without_mutating_refs`.
- [ ] Assert `devflow status --json` includes a per-task `worker_lane` object for Git-native tasks with:
  - `workspace_mode == "git-worktree"`;
  - `worker_branch == "devflow/task-0001/shell"`;
  - `readiness_status == "ready"`;
  - `next_safe_action == "devflow task promote task-0001"`.
- [ ] Assert `devflow supervisor packet --json` includes the same lane object on the task record and includes lane evidence paths in `evidence_paths`.
- [ ] Assert `_invoke_read_only()` still proves these commands do not mutate files, refs, or Git status.
- [ ] Update `src/devflow/control_room/supervisor_surface.py`:
  - call `git_worker_lane_summary()` while building status task records;
  - include `worker_lane` only for Git-native tasks;
  - append lane evidence paths to existing evidence path output after de-duplicating.
- [ ] Re-run:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_supervisor_operating_surface.py -q
```

## Task 5: Surface Lane Summary in the Operating Layer

Write tests first.

- [ ] In `tests/test_operating_layer.py`, add `test_operating_layer_snapshot_includes_git_worker_lane_summary`.
- [ ] Initialize a temporary Git repo in the test using the same commands already used in `tests/test_supervisor_operating_surface.py`.
- [ ] Create, run, verify, and preview a Git-native task.
- [ ] Assert `build_operating_layer_snapshot(tmp_path).model_dump(mode="json")["tasks"][0]["worker_lane"]` contains:
  - `workspace_mode == "git-worktree"`;
  - `worker_branch == "devflow/task-0001/shell"`;
  - `worktree_path == ".devflow/worktrees/task-0001/shell"`;
  - `readiness_status == "ready"`;
  - `next_safe_action == "devflow task promote task-0001"`.
- [ ] Assert `detail["review_summary"]` has a `Worker lane` item and a `Lane readiness` item.
- [ ] Update `src/devflow/control_room/operating_layer.py`:
  - add an `OperatingLayerWorkerLane` Pydantic model;
  - add `worker_lane: OperatingLayerWorkerLane | None = None` to `OperatingLayerTask`;
  - populate it in `_task_card()`;
  - add worker lane rows to `_task_review_summary()`.
- [ ] Update `src/devflow/control_room/operating_layer_script.py` to render the lane summary in the selected task review panel.
- [ ] Update `src/devflow/control_room/operating_layer_styles.py` for a compact lane block that matches existing task review styles.
- [ ] Update `test_operating_layer_assets_facade_keeps_split_asset_contract` if new CSS/JS marker strings are introduced.
- [ ] Re-run:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_operating_layer.py -q
```

## Task 6: Harden Refusal and Recovery Output

Write tests first.

- [ ] In `tests/test_git_worktree_promotion.py`, add `test_git_worker_lane_summary_reports_dirty_and_head_changed_recovery`.
- [ ] Cover two states:
  - uncommitted changes after verification produce `readiness_status == "dirty"` and next action `devflow task verify task-0001 --shell "<command>"`;
  - a new worker branch commit after verification produces `head_matches_verified is False`, `readiness_status == "dirty"`, and the same verification next action.
- [ ] Add `test_promote_preview_and_promote_refusals_include_lane_next_action`.
- [ ] Assert promotion refusal output for stale verified commit includes:
  - `worker HEAD differs from verified commit`;
  - `next_safe_action: devflow task verify task-0001 --shell "<command>"`.
- [ ] If `promote-preview` reports stale baseline or conflict, assert its output includes:
  - `promotion_readiness: not_ready` or `promotion_readiness: blocked`;
  - `next_safe_action: devflow task promote-preview task-0001`.
- [ ] Update `src/devflow/control_room/git_worktree.py`, `src/devflow/control_room/promotion.py`, `src/devflow/control_room/readiness.py`, or `src/devflow/control_room/service.py` only where refusal formatting currently loses the actionable lane next step.
- [ ] Keep refusal behavior conservative. Do not add automatic rebase, merge conflict resolution, or force-promotion flows.
- [ ] Re-run:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_git_worktree_promotion.py tests/test_task_finalize.py -q
```

## Task 7: Add Git-Native Lane Dogfood Coverage

- [ ] Inspect the existing dogfood harness before editing:

```bash
rg -n "dogfood|production-readiness|Dogfood" src/devflow/control_room tests -S
```

- [ ] Add a production-readiness dogfood case that performs the acceptance scenario from the design doc:
  - create two `--git-worktree` tasks from clean `main`;
  - run shell workers that touch disjoint files;
  - finalize or commit both worker lanes;
  - verify exact worker heads;
  - preview both;
  - promote one;
  - confirm the second lane reports stale baseline or clean readiness accurately after `main` advances;
  - dry-run cleanup for the promoted lane;
  - apply cleanup only where the harness already permits Git cleanup mutations;
  - confirm canonical `.devflow/tasks/<task_id>/` evidence remains.
- [ ] If the current dogfood harness cannot safely apply cleanup, implement the case as a dry-run cleanup proof and document the apply step in the handoff risk.
- [ ] Add or extend a focused test for the dogfood case in the existing dogfood test file.
- [ ] Re-run:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests -k dogfood -q
PYTHONPATH=src:. .venv/bin/devflow dogfood run --suite production-readiness
```

## Task 8: Update Active Docs and Handoff

- [ ] Update `docs/control-room-mvp.md` to say Milestone 19 is the active next hardening milestone after Milestone 18 closed on `main`.
- [ ] Update `docs/agent-handoff.md` so it no longer says Milestone 18 is awaiting merge/push.
- [ ] Update `docs/architecture/local-operating-layer-ui.md` so the next safe slice is Git-native lane visibility and hardening, not Milestone 18 closure.
- [ ] Update `docs/architecture/git-native-worker-isolation-and-promotion.md` with the implemented Milestone 19 lane summary contract.
- [ ] Write a compact handoff in `docs/handoffs/` using `docs/handoff-template.md`.
- [ ] Run stale-context scans over active docs:

```bash
rg -n "Milestone 18.*feature[ -]branch|feature[ -]branch.*Milestone 18|human-approved merge.*push|Pending Operating-Layer|next safe UI" docs README.md AGENTS.md -S
```

## Task 9: Verification and Checkpoint

- [ ] Run focused Git-native and surface tests:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest \
  tests/test_git_worktree_promotion.py \
  tests/test_task_finalize.py \
  tests/test_operating_layer.py \
  tests/test_supervisor_operating_surface.py \
  -q
```

- [ ] Run dogfood:

```bash
PYTHONPATH=src:. .venv/bin/devflow dogfood run --suite production-readiness
```

- [ ] Run full release gate:

```bash
./scripts/release-check.sh
```

- [ ] Report whether packaging validation ran. If `python-build` or `twine` is unavailable, record that explicit risk.
- [ ] Run whitespace and status checks:

```bash
git diff --check
PYTHONPATH=src:. .venv/bin/devflow git status
```

- [ ] Create a Dev-Flow checkpoint after verification:

```bash
PYTHONPATH=src:. .venv/bin/devflow git checkpoint --message "feat: harden git-native worker lanes"
```

- [ ] Do not push or merge without explicit human approval.

## Completion Criteria

- Git-native task lane state is visible in CLI, status JSON, supervisor packet JSON, and the operating layer.
- All surfaces agree on branch, worktree path, base/head/verified commit, dirty state, promotion readiness, conflict prediction, and next safe action.
- Promotion refuses stale, dirty, head-changed, missing, and conflict states with concrete recovery commands.
- Cleanup remains dry-run-first and preserves canonical task evidence.
- Two-lane dogfood passes or reports an explicit harness limitation.
- The focused test set, dogfood suite, `git diff --check`, and release gate results are recorded in the handoff.
