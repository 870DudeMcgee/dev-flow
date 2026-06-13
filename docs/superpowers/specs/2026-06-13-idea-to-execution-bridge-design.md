# Idea-To-Execution Bridge Design

Date: 2026-06-13
Status: Planned; implementation not started

## Purpose

Milestone 13 should connect the new Idea Foundry intake queue to Dev-Flow's existing goal and task machinery without making idea promotion automatic. The goal is to let a human-reviewed idea become an explicit goal scaffold or an explicit task record after the idea has already been classified and promoted as decision evidence.

This is a bridge from intent to controlled execution state. It is not a classifier, scheduler, router, worker runtime, or provider adapter.

## Product Fit

This moves Dev-Flow toward the North Star by closing a visible, local-first path from rough intent to isolated work. The human remains in control at each boundary: capture, classify, promote decision, create goal or task, run workers, verify, preview promotion, and promote code.

Periodic self-check:

- This builds the control room, not a coding agent.
- It improves visibility by linking ideas to concrete goal/task artifacts.
- It reduces hidden context by preserving raw idea, classification, promotion, and creation evidence.
- It protects the main repo by creating only Dev-Flow state, never running workers or promoting code.
- It is useful in the MVP because the control loop gains a reviewable intake-to-execution handoff without speculative automation.

## Approaches Considered

Recommended: add explicit `devflow idea create-goal` and `devflow idea create-task` commands. This keeps the boundary clear, gives the operator an obvious next command after `idea promote`, and lets tests enforce that creation does not imply worker execution or verification.

Alternative: teach `devflow idea promote` to create goals or tasks with an extra flag. This is compact, but it overloads promotion decision evidence with state creation and weakens the current safety language that promotion creates no work.

Alternative: leave Idea Foundry as decision evidence only. This is safe, but it leaves a manual copy-paste gap between useful intake evidence and actual Dev-Flow goal/task state.

## Scope

Add this first bridge slice:

- `devflow idea create-goal <idea_id>`
- `devflow idea create-goal <idea_id> --dry-run`
- `devflow idea create-task <idea_id>`
- `devflow idea create-task <idea_id> --dry-run`

Creation commands require a matching prior `devflow idea promote` decision. They must write durable cross-links so a future agent can answer both directions:

- Which idea produced this goal or task?
- Which goal or task was created from this idea?

## Non-Goals

- No automatic creation during `idea promote`.
- No provider-backed classification.
- No local model classification.
- No autonomous routing.
- No worker execution.
- No verification execution.
- No promotion preview or code promotion.
- No commits, pushes, pull requests, or branch operations except the existing optional task worktree creation path when explicitly requested.
- No database, vector search, embeddings, RAG, hidden memory, or background daemon.
- No writes under `src/devflow/_legacy/`.

## Preconditions

`devflow idea create-goal <idea_id>` requires:

- the idea exists
- the idea is not archived
- `status` is `promoted`
- `promotion_target` is `goal`
- `maturity` is `goal_ready`
- no goal has already been created from this idea

`devflow idea create-task <idea_id>` requires:

- the idea exists
- the idea is not archived
- `status` is `promoted`
- `promotion_target` is `task`
- `maturity` is `task_ready`
- no task has already been created from this idea

Repeated creation should fail clearly by default. A duplicate override is intentionally out of scope for the first slice.

## Data Model

Existing idea evidence remains under:

```text
.devflow/ideas/<idea_id>/
  idea.json
  raw.md
  classification.md
  promotion.md
  events.jsonl
```

Milestone 13 adds optional creation fields to `idea.json`:

- `created_goal_id`
- `created_goal_path`
- `created_task_id`
- `created_task_path`
- `created_from_idea_at`
- `creation_command`

New idea-side evidence:

```text
.devflow/ideas/<idea_id>/goal-brief.md
.devflow/ideas/<idea_id>/task-brief.md
```

`goal-brief.md` is the source brief passed to the existing goal scaffold path. `task-brief.md` is the source summary copied into the task evidence.

New goal-side evidence:

```text
.devflow/goals/<goal_id>/idea-link.yaml
```

New task-side evidence:

```text
.devflow/tasks/<task_id>/idea-link.yaml
.devflow/tasks/<task_id>/idea.md
```

`idea-link.yaml` records `schema_version`, `idea_id`, `idea_path`, `promotion_target`, `maturity`, `source_raw_path`, `source_classification_path`, `source_promotion_path`, and `created_from_idea: true`.

## Command Behavior

### `devflow idea create-goal <idea_id>`

Creates a durable goal scaffold from a promoted goal-ready idea.

Options:

- `--title <title>` optional title override
- `--goal-id <goal_id>` optional explicit goal id
- `--dry-run` preview without writes

If `--goal-id` is supplied and that goal already exists, the command refuses before writing evidence. Otherwise it writes `.devflow/ideas/<idea_id>/goal-brief.md`, calls the existing goal scaffold path, writes `.devflow/goals/<goal_id>/idea-link.yaml`, updates `idea.json` with the created goal id/path, and appends an idea event named `goal_created`.

It prints the created goal id/path and the next safe command, such as `devflow goal show G-0001`.

### `devflow idea create-task <idea_id>`

Creates a normal Dev-Flow task from a promoted task-ready idea.

Options:

- `--title <title>` optional title override
- `--git-worktree` opt into the existing Git-native task lane
- `--dry-run` preview without writes

The command calls the existing task creation service, writes `.devflow/tasks/<task_id>/idea-link.yaml`, writes `.devflow/tasks/<task_id>/idea.md`, updates `idea.json` with the created task id/path, and appends an idea event named `task_created`.

It prints the created task id/path and the next safe command, such as `devflow task show task-0001`.

Creating a task must not run the worker, run verification, apply patches, or promote code. If `--git-worktree` is supplied, it uses the existing task creation path for worktree-backed tasks and does not add new branch semantics.

## Dry-Run Behavior

Dry-run commands perform the same precondition checks and render the proposed title, target id when known, link paths, and next command. They must not write files, append events, create goals, create tasks, create worktrees, run workers, or mutate Git.

Supervisor classification should treat dry-run forms as read-only. Actual creation commands are approval-required task-state mutations.

## Error Handling

Failures should be plain and actionable:

- invalid idea id: `Invalid idea id: <value>`
- missing idea: `Idea not found: <idea_id>`
- missing promotion decision: `Idea must be promoted to <target> before creation.`
- wrong target: `Idea promotion target is <actual>, not <expected>.`
- wrong maturity: `Creation requires maturity <required>.`
- archived idea: `Archived idea cannot create a goal or task.`
- duplicate creation: `Idea already created <goal|task> <id>.`
- existing explicit goal id: `Goal already exists: <goal_id>`

Failed precondition checks should not write evidence.

## Safety And Supervisor Policy

Supervisor-safe read-only commands:

- `devflow idea create-goal <idea_id> --dry-run`
- `devflow idea create-task <idea_id> --dry-run`

Approval-required task-state commands:

- `devflow idea create-goal <idea_id>`
- `devflow idea create-task <idea_id>`

These commands create Dev-Flow state only. They must not call providers, classify with models, run workers, verify, promote code, commit, push, open pull requests, or change any source file outside task workspaces/worktrees.

## Documentation Alignment

After implementation, active docs should document the bridge as current behavior:

- `README.md`
- `docs/control-room-mvp.md`
- `docs/mvp-contract.md`
- `docs/roadmap.md`
- `docs/architecture/patch-evidence-ladder.md`

Until implementation lands, docs should describe Milestone 13 as the next planned slice, not as stable runtime behavior.

## Test Strategy

Focused tests should cover:

- create-goal refuses unpromoted, wrong-target, wrong-maturity, archived, and duplicate ideas
- create-goal writes a goal scaffold and bidirectional idea/goal links
- create-goal does not create tasks, run workers, verify, promote, commit, or push
- create-task refuses unpromoted, wrong-target, wrong-maturity, archived, and duplicate ideas
- create-task writes a task record and bidirectional idea/task links
- create-task leaves the task in created/not-run state
- dry-run variants do not mutate files or append events
- `idea show` surfaces created goal/task refs
- supervisor classification distinguishes read-only dry-runs from approval-required creation

## Acceptance Criteria

- `devflow idea create-goal` and `devflow idea create-task` exist.
- Both commands require explicit prior promotion decisions.
- Both commands support `--dry-run` without mutation.
- Created goals and tasks link back to source ideas.
- Source ideas link forward to created goals or tasks.
- Creation commands do not run workers, verification, promotion, commits, pushes, providers, or routing.
- Supervisor policy classifies the commands safely.
- Active docs stop describing the idea-to-execution bridge as an undecided question after implementation.
- Focused tests pass.
