# Milestone 19 Git-Native Worker Lane Hardening Design

## Goal

Make the opt-in Git-native worker lane trustworthy enough for real parallel control-room dogfood.

Milestone 19 does not make `--git-worktree` the default. It hardens the existing opt-in path so a human operator can create Git worktree tasks, understand each worker lane's exact Git state, verify a worker commit, preview promotion, recover from stale or dirty states, promote safely, and clean up owned worktree resources without losing canonical task evidence.

## Why This Milestone Comes Next

Milestones 16-18 established the local operating layer, registry/context routing evidence, and read-only visibility over batch and task state. The next highest-leverage step is not a new worker runtime. The control room needs a durable lane model first:

- tasks need isolated workspaces that survive worker crashes and operator context switches;
- lane state needs to be visible in CLI, supervisor, and browser surfaces;
- promotion refusal needs to explain exactly what changed and what to do next;
- cleanup needs to be safe enough for repeated dogfood.

This strengthens the product's core promise: local-first supervision of replaceable coding workers.

## Product Boundary

In scope:

- Git worktree task lanes created by the existing `--git-worktree` path.
- Shell workers as the only code-changing runtime.
- Read-only lane evidence for browser and supervisor surfaces.
- Human-approved preview, verification, promotion, cleanup, and archival.
- Deterministic refusal reasons and concrete next safe actions.
- Dogfood that creates two Git-native task lanes from the same clean main baseline.

Out of scope:

- Provider-backed non-shell adapters.
- Autonomous routing.
- Automatic promotion, push, pull request creation, or conflict resolution.
- Making Git-native worktrees the default workspace mode.
- Browser-triggered arbitrary worker execution.
- New task scheduling, memory, DAG, or old software-factory workflows.

## Operator Story

An operator starts from clean `main`, creates two tasks with `--git-worktree`, and runs shell commands in each isolated worktree. Each lane records the base branch, base commit, worker branch, worker worktree path, current head, dirty status, verification result, promotion preview, conflict prediction, and cleanup status.

The operator can answer these questions without manually inspecting `.devflow/` files:

- Which branch and worktree belongs to this task?
- What base commit did this lane fork from?
- Has the worker branch diverged from the task's verified commit?
- Is the lane dirty after verification?
- Is `main` or `origin/main` stale relative to the lane baseline?
- Would promotion conflict with current `main`?
- What is the next safe action for this lane?
- Which cleanup command removes only owned worktree resources while retaining task evidence?

## Architecture

Milestone 19 introduces a first-class worker lane projection built on top of the existing Git-native helpers.

Current durable files remain canonical:

- `.devflow/tasks/<task_id>/task.json`
- `.devflow/tasks/<task_id>/workers/<worker_id>/git.json`
- `.devflow/tasks/<task_id>/workers/<worker_id>/diff.patch`
- `.devflow/tasks/<task_id>/workers/<worker_id>/diff-summary.json`
- `.devflow/tasks/<task_id>/workers/<worker_id>/promotion-preview.json`
- `.devflow/tasks/<task_id>/promotion-preview.json` as a backward-compatible preview fallback when present
- `.devflow/tasks/<task_id>/verification.json`

The new lane projection is a derived read model. It must not replace these files and must not require a separate database.

### Read Model

Add a read-only helper in `src/devflow/control_room/git_worktree.py`:

```python
def git_worker_lane_summary(root: Path, task: TaskRecord, worker_id: str | None = None) -> dict[str, Any] | None:
    """Return a read-only summary of an opt-in Git worker lane."""
```

The helper should return `None` for non-Git-worktree tasks. For Git-native tasks, it should read existing evidence and run read-only Git commands where needed. It must not write `git.json`, `promotion-preview.json`, or diff artifacts. Commands that intentionally refresh or write evidence should keep using `refresh_git_worker_evidence()` and `build_git_promotion_preview()`.

Suggested summary shape:

```json
{
  "schema": 1,
  "task_id": "task-0001",
  "worker_id": "shell",
  "workspace_mode": "git-worktree",
  "worktree_path": ".devflow/worktrees/task-0001/shell",
  "worker_branch": "devflow/task-0001/shell",
  "base_branch": "main",
  "base_commit": "abc123",
  "base_current_commit": "def456",
  "base_stale": true,
  "origin_base_commit": "def456",
  "origin_base_stale": true,
  "head_commit": "987654",
  "dirty": false,
  "verified_commit": "987654",
  "head_matches_verified": true,
  "promotion_preview": {
    "status": "ready",
    "conflict_prediction": "clean",
    "changed_files": ["src/devflow/control_room/example.py"]
  },
  "readiness": {
    "status": "ready",
    "errors": [],
    "warnings": ["main has advanced since lane creation"]
  },
  "cleanup": {
    "worktree_owned": true,
    "branch_owned": true,
    "archived_branch": null
  },
  "next_safe_action": "devflow task promote-preview task-0001"
}
```

Field names may be adjusted to match existing model conventions, but the projection must carry the same information.

### Surfaces

CLI:

- `devflow task show <task_id>` shows a compact Git worker lane section for Git-native tasks.
- `devflow task review-ready <task_id>` includes lane readiness and blocker details.
- `devflow task promote-preview <task_id>` keeps writing durable promotion evidence and prints next safe action on refusal.
- `devflow worktree list`, `devflow branch list`, and `devflow task cleanup` expose owned/orphaned status consistently.

Supervisor:

- Supervisor task summaries include `workspace_mode`, worker branch, worktree path, head commit, dirty flag, verified commit, readiness status, and next safe action.
- Supervisor commands remain safe and explicit. No route may promote, push, or run arbitrary commands without the existing human-controlled command path.

Operating layer:

- The browser operating layer renders a read-only lane block for Git-native tasks.
- The block uses the same status vocabulary as the CLI: `ready`, `blocked`, `stale`, `dirty`, `conflict`, `unverified`, `missing`.
- Existing exact browser actions may remain for verification and promotion. No new arbitrary execution action is added.

## Status Vocabulary

Use a small deterministic vocabulary across all surfaces:

- `ready`: lane has a clean worktree, verified head, current preview, and no promotion blockers.
- `unverified`: lane has a worker head that has not been verified.
- `dirty`: lane has uncommitted changes or changed after verification.
- `stale`: the base branch or origin baseline advanced since lane creation.
- `conflict`: promotion preview predicts conflicts or actual promotion hit conflicts.
- `missing`: expected worktree, branch, base commit, or evidence is missing.
- `blocked`: more than one readiness error is present or the lane is not safe to promote.

Each non-ready state must include a human action, for example:

- commit or discard changes inside the worker worktree;
- rerun exact verification for the current worker head;
- rebuild promotion preview against current `main`;
- inspect conflict report and resolve manually;
- run dry-run cleanup before applying cleanup;
- recreate the task lane when branch/worktree identity is corrupted.

## Evidence Rules

- Canonical task evidence stays under `.devflow/tasks/<task_id>/`.
- Worktree directories stay under `.devflow/worktrees/`.
- Worker branches stay under `devflow/<task_id>/<worker_id>`.
- Archived worker branches stay under `devflow/archive/<task_id>/<worker_id>-<timestamp>`.
- Cleanup may remove worktree directories and archive owned branches, but it must not remove canonical task evidence by default.
- Read-only summaries may compute live Git state, but they must not mutate task evidence.

## Acceptance Scenario

The milestone is done when this scenario passes in a real repository:

1. Start from clean `main`.
2. Create two tasks using `--git-worktree`.
3. Confirm each task has its own worktree path and worker branch.
4. Run one shell worker command in each worktree that changes a disjoint file.
5. Commit each lane's work inside its worker branch.
6. Verify each lane's exact worker head.
7. Confirm `doctor --strict`, `task show`, `task review-ready`, `task promote-preview`, `worktree list`, `branch list`, supervisor output, and operating-layer snapshot agree on lane state.
8. Promote one lane after preview and approval.
9. Confirm the second lane reports stale baseline or clean readiness accurately after `main` advances.
10. Cleanup/archive the promoted lane resources while preserving `.devflow/tasks/<task_id>/`.
11. Confirm strict doctor reports no owned-resource integrity gaps.

## Test Strategy

Focused tests:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest \
  tests/test_git_worktree_promotion.py \
  tests/test_task_finalize.py \
  tests/test_operating_layer.py \
  tests/test_supervisor_operating_surface.py \
  -q
```

Dogfood:

```bash
PYTHONPATH=src:. .venv/bin/devflow dogfood run --suite production-readiness
```

Full release gate:

```bash
./scripts/release-check.sh
```

The release gate should run packaging validation when `python-build` and `twine` are installed. If those tools are unavailable, the handoff must explicitly report the skipped packaging risk.

## Product North Star Self-Check

- Simpler control room: yes, this milestone improves the existing local-first worker lane instead of adding orchestration layers.
- Replaceable workers: yes, the lane model is worker-runtime agnostic while only shell remains active for code changes.
- Human control: yes, promotion, cleanup, and verification stay explicit and inspectable.
- No legacy workflow revival: yes, no claims, DAGs, memory, local-model delegation, or old patch gates are introduced.
- No premature provider work: yes, non-shell adapters remain deferred until the Git-native lane is reliable.
