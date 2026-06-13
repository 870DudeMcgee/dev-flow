# Idea Foundry MVP Design

Date: 2026-06-13
Status: Draft; ready for review and implementation handoff

## Purpose

Milestone 12 should turn Idea Foundry from a roadmap concept into a small, local-first intake surface. The goal is to capture rough product or engineering ideas before they are ready to become goals or tasks, classify them with human-supplied context, and record promotion decisions without automatically creating work.

This is an intake and review layer, not a worker runtime. It must not route models, call providers, create tasks automatically, create goals automatically, use a database, or change promotion behavior.

## Product Fit

This moves Dev-Flow toward the North Star by making early work visible and recoverable before it becomes parallel worker execution. It keeps state durable and inspectable, and it preserves the human-controlled boundary between "idea", "goal", and "task".

Periodic self-check:

- This builds the control room, not a coding agent.
- It improves visibility by giving raw ideas durable state and status.
- It reduces hidden context by moving idea notes out of chat-only memory.
- It protects the main repo by not creating tasks, workers, branches, commits, or promotions.
- It is useful in the MVP because it gives the control loop a human-reviewed intake queue without speculative automation.

## Scope

Implement a first vertical slice with these commands:

- `devflow idea capture "<text>"`
- `devflow idea list`
- `devflow idea show <idea_id>`
- `devflow idea classify <idea_id>`
- `devflow idea promote <idea_id> --to goal|task`
- `devflow idea archive <idea_id>`

The first slice stores ideas under project-local `.devflow/ideas/` because current Dev-Flow state authority is project-local `.devflow/`, not `projects/<project>/01-ideas/`.

## Non-Goals

- No automatic goal creation.
- No automatic task creation.
- No provider, local model, scout, or routing calls.
- No background classifier.
- No database, vector search, embeddings, RAG, or hidden memory.
- No dashboard or operating-layer UI changes in the first slice.
- No writes under `src/devflow/_legacy/`.

## Data Model

Each idea is stored under:

```text
.devflow/ideas/<idea_id>/
  idea.json
  raw.md
  classification.md
  promotion.md
  events.jsonl
```

IDs use `I-0001`, `I-0002`, and so on.

`idea.json` fields:

- `schema_version`: current Dev-Flow schema version
- `id`: idea id
- `title`: short title, derived from raw text if omitted
- `status`: one of `inbox`, `classified`, `promoted`, `archived`
- `maturity`: one of `spark`, `concept`, `candidate`, `goal_ready`, `task_ready`
- `tags`: list of human-supplied tags
- `source`: source label such as `manual`, `chat`, or `handoff`
- `promotion_target`: `goal`, `task`, or null
- `created_at`, `updated_at`, `classified_at`, `promoted_at`, `archived_at`
- `raw_path`, `classification_path`, `promotion_path`

`raw.md` contains the captured idea text. `classification.md` contains the human-supplied classification note. `promotion.md` records the human promotion decision and the next suggested manual command, but does not execute that command.

## Command Behavior

### `devflow idea capture "<text>"`

Creates an `inbox` idea with maturity `spark`, writes `raw.md`, writes `idea.json`, appends a `created` event, and prints the id, status, maturity, and path.

Options:

- `--title <title>` optional title override
- `--source <source>` defaults to `manual`
- `--tag <tag>` repeatable

### `devflow idea list`

Prints a compact table of ideas. It should support `--status <status>` for filtering. Missing `.devflow/ideas/` prints `No ideas found.`

### `devflow idea show <idea_id>`

Prints metadata and the raw/classification/promotion note sections that exist. Invalid ids fail cleanly.

### `devflow idea classify <idea_id>`

Updates an idea from `inbox` or `classified` to `classified`, records maturity and tags, writes `classification.md`, and appends a `classified` event.

Options:

- `--maturity spark|concept|candidate|goal_ready|task_ready`
- `--note <text>` optional human note
- `--tag <tag>` repeatable

This command does not infer classification and does not call a model.

### `devflow idea promote <idea_id> --to goal|task`

Records a promotion decision and sets status to `promoted`. It writes `promotion.md`, updates `idea.json`, and appends a `promoted` event.

Promotion preconditions:

- `--to goal` requires maturity `goal_ready`
- `--to task` requires maturity `task_ready`
- archived ideas cannot be promoted

The command must print `created_goal: no` and `created_task: no`. It may include a suggested next manual command, but it must not run that command.

### `devflow idea archive <idea_id>`

Sets status to `archived`, records an archive reason, and appends an `archived` event. It does not delete idea evidence.

## Safety And Supervisor Policy

Supervisor-safe read-only commands:

- `devflow idea list`
- `devflow idea show`

Approval-required evidence-writing commands:

- `devflow idea capture`
- `devflow idea classify`
- `devflow idea promote`
- `devflow idea archive`

Idea promotion is not task promotion. It writes intake evidence only and must not create tasks, goals, branches, worker runs, verification runs, commits, pushes, pull requests, or promotion previews.

## Documentation Alignment

After implementation, active docs should document Idea Foundry as current behavior:

- `README.md`
- `docs/control-room-mvp.md`
- `docs/mvp-contract.md`
- `docs/roadmap.md`
- `docs/architecture/patch-evidence-ladder.md`

The roadmap should mark Milestone 12 implemented only after command behavior, tests, docs, and a clean checkpoint land.

## Test Strategy

Focused tests should cover:

- capture creates `.devflow/ideas/I-0001/idea.json`, `raw.md`, and `events.jsonl`
- list/show render captured ideas
- classify records maturity, tags, and `classification.md`
- promotion refuses ideas that are not `goal_ready` or `task_ready`
- promotion records a decision without creating `.devflow/goals/` or `.devflow/tasks/`
- archive preserves evidence and removes the idea from active default views only if the list command implements an active filter
- invalid ids fail cleanly
- supervisor classification treats read-only and evidence-writing idea commands correctly

## Acceptance Criteria

- `devflow idea capture/list/show/classify/promote/archive` are implemented.
- Idea state lives under project-local `.devflow/ideas/`.
- All writes use atomic file writes where replacement is required.
- Events are append-only JSONL evidence.
- Promotion records a human decision but creates no goal or task.
- Supervisor policy classifies idea commands safely.
- Active docs no longer describe Idea Foundry as future-only after implementation.
- Focused tests pass.

## Open Decisions For Implementation

- Keep `devflow idea promote` as a decision recorder in this slice. A later milestone can add explicit `devflow idea create-goal` or `devflow idea create-task` commands if Josh wants that boundary promoted.
- Keep search out of this slice. It can be added later after list/show/classify/promotion behavior is stable.
