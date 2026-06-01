# Git-Native Worker Isolation And Promotion

Status: initial opt-in vertical slice implemented. The default task path remains copy-workspace unless `devflow task create --git-worktree` is used.

## Thesis

The current Dev-Flow runtime is a strong copy-workspace control-room MVP. Production Dev-Flow should make Git the worker isolation and promotion substrate:

```text
Git-isolated workers
+ Dev-Flow-owned state
+ verification evidence
+ human-controlled promotion
```

Dev-Flow remains the control layer. Git branches and worktrees become the durable isolation layer.

## Current And Target Runtime Shapes

Current MVP shape:

```text
.devflow/workspaces/<task_id>/
```

Target production shape:

```text
.devflow/worktrees/<task_id>/<worker_id>/
branch: devflow/<task_id>/<worker_id>
base: main HEAD at assignment time
```

The copy-workspace runtime remains valid for the default contract. The opt-in Git path replaces the worker execution lane with a Git worktree and branch while keeping filesystem state, logs, verification evidence, and human promotion gates under Dev-Flow control.

## Worker Git Record

Each worker attempt needs a first-class Git record:

```json
{
  "task_id": "task-001",
  "worker_id": "codex-implementation",
  "base_branch": "main",
  "base_commit": "<sha>",
  "worker_branch": "devflow/task-001/codex-implementation",
  "worktree_path": ".devflow/worktrees/task-001/codex-implementation",
  "head_commit": "<sha>",
  "dirty": false
}
```

This record makes the isolation lane inspectable, recoverable, and promotable without treating worker-written prose as truth.

## Worker Attempts

Production parallelism should model attempts explicitly:

```text
task
  worker_attempt A
  worker_attempt B
  verifier worker
  review worker
```

Each attempt gets its own branch, worktree, logs, Git facts, diff evidence, and verification evidence. A planner, implementation worker, test worker, review worker, alternate implementation worker, local model worker, and frontier model worker must not share one mutable lane.

Recommended artifact layout:

```text
.devflow/tasks/<task_id>/workers/<worker_id>/git.json
.devflow/tasks/<task_id>/workers/<worker_id>/diff.patch
.devflow/tasks/<task_id>/workers/<worker_id>/diff-summary.json
.devflow/tasks/<task_id>/workers/<worker_id>/verification.json
.devflow/tasks/<task_id>/workers/<worker_id>/promotion-preview.json
.devflow/tasks/<task_id>/workers/<worker_id>/logs/worker.log
.devflow/tasks/<task_id>/workers/<worker_id>/logs/verify.log
```

`task.yaml` remains canonical task state. Worker Git artifacts are canonical-adjacent evidence for isolation, verification, and promotion readiness.

## Verification Binding

Verification must bind to the branch commit that was actually checked:

```json
{
  "worker_id": "codex-implementation",
  "branch": "devflow/task-001/codex-implementation",
  "verified_commit": "<sha>",
  "base_commit": "<sha>",
  "main_head_at_verification": "<sha>",
  "dirty_at_verification": false,
  "command": "pytest",
  "exit_code": 0,
  "status": "passed"
}
```

Promotion must refuse when:

- worker HEAD differs from `verified_commit`
- the worker worktree is dirty after verification
- main HEAD moved and the stale baseline is unresolved
- the merge preview predicts conflicts that the human has not explicitly accepted as a resolver task

## Git-Native Promotion Preview

`devflow task promote-preview` should evolve from copy-workspace preview into a Git-native readiness report:

```text
task id
worker id
base commit
main current HEAD
worker branch HEAD
merge-base
baseline stale? yes/no
changed files
deleted files
renamed files
untracked files
binary files
conflict prediction
verification status
promotion readiness
```

Promotion should be framed as:

```text
worker branch proposes a diff
Dev-Flow previews the diff
verification proves the branch commit
human promotes the branch or diff
Git handles merge/conflict semantics
```

It should not be framed as blind file copy-back from a scratchpad.

## Git Readiness Checks

`devflow doctor --strict` should add Git integrity checks after the worktree runtime exists:

- worker branch exists
- worker worktree exists
- recorded worktree path is under `.devflow/worktrees/`
- worktree HEAD matches the recorded head
- base commit exists
- worker branch descends from the recorded base
- verification commit still equals worker HEAD
- no dirty worktree after verification
- main checkout is clean before promotion
- promotion target is clean
- merge preview is clean or conflicts are explicitly surfaced
- no orphaned worktrees
- no orphaned `devflow/*` branches
- no branch is shared by two workers

## Cleanup And Recovery

Git-native isolation includes cautious cleanup tools. They default to dry-run behavior and require `--apply` before mutating anything:

```bash
devflow task cleanup <task_id> --dry-run
devflow task cleanup <task_id> --apply
devflow worktree list
devflow worktree prune --dry-run
devflow worktree prune --apply
devflow branch list
devflow branch archive <branch> --dry-run
devflow branch archive <branch> --apply
```

These commands report proposed worktree and branch actions before mutating anything. Branch cleanup archives task branches under `devflow/archive/` instead of deleting them.

## Conflict UX

Dev-Flow should make Git conflicts operationally visible instead of trying to hide them.

Example refusal:

```text
promotion refused: merge conflict predicted
conflict files:
  src/foo.py
suggested next action:
  devflow task create "Resolve conflict for task-001 worker codex-implementation"
```

Conflict resolution remains human-controlled work unless a future contract explicitly introduces a bounded resolver worker.

## Implemented Vertical Slice

The initial implementation proves this sequence:

1. Create a task with `devflow task create --git-worktree`.
2. Create a task branch from current `main` HEAD.
3. Run the shell worker inside that worktree.
4. Record base commit, branch, worktree path, and HEAD.
5. Run verification inside that worktree.
6. Bind verification to worker HEAD commit.
7. Show a Git-native promotion preview.
8. Refuse promotion if worker HEAD changed after verification.
9. Refuse promotion if main moved and the conflict or stale baseline is unresolved.
10. Promote with Git-aware mechanics instead of blind copy-back.

## Out Of Scope For This Milestone

- provider-backed non-shell adapters
- autonomous routing
- automatic push, pull request, or release creation
- hiding merge conflicts from the human
- OS-level sandboxing as the center of the milestone
- resurrecting legacy `src/devflow/worktrees.py` behavior without reconciling it with this contract