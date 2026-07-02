# Dev-Flow Domain Context

Status: active vocabulary for architecture reviews.

This file records domain terms used by architecture and refactoring work. Product authority still lives in `PRODUCT_NORTH_STAR.md` and `docs/control-room-mvp.md`; this file exists so agents use stable names when discussing Modules, Interfaces, Seams, and Adapters.

## Terms

### Control room

The local-first Dev-Flow operating surface that lets the operator see tasks, workers/models, evidence, verification, review readiness, and next safe actions without digging through raw logs.

### Operating layer

The active browser product served by `devflow operating-layer serve`. It is a read-oriented projection over filesystem-backed Dev-Flow state plus a narrow approval-gated browser action path.

### Task

A Dev-Flow unit of work with durable state under `.devflow/tasks/<task_id>/`. A task owns its title, status, workspace, worker/model identity, logs, evidence, verification, close state, and promotion readiness.

### Worker lane

The operator-facing view of work owned by a worker or model for a task. A worker lane should show task title, status, worker/model, last update, evidence, and next action.

### Review queue

The operator-facing list of tasks that need verification, review, human decision, or promotion action.

### Evidence stream

The operator-facing timeline or list of concrete task artifacts: events, logs, worker output, verification records, promotion previews, and other review evidence.

### Next safe action

The most useful action Dev-Flow can recommend without hiding safety requirements. It must name the task or project, expose the exact command when applicable, and make human approval requirements visible.

### Task workbench

The operator-facing projection that turns task state into the first usable work surface: selected task, Worker lanes, Review queue, Evidence stream, task controls, gate progress, worker/model identity, and next safe actions.

The Task workbench is not canonical state. It is a derived read model for usability and should remain backed by existing task artifacts, worker evidence, verification artifacts, and promotion readiness evidence.

### Repository cleanup

A source-tree hygiene activity that classifies repository material before changing, archiving, untracking, or deleting it.

Repository cleanup candidates are classified as active product, compatibility bridge, generated/local runtime state, historical reference, future roadmap, stale context candidate, or stale artifact.

### Stale context candidate

A document or reference whose current accuracy is untrusted until reconciled against active product intent, code, tests, live Dev-Flow behavior, and fresh architecture evidence.

## Flagged ambiguities

- "cleanup" was used to mean both task-owned runtime cleanup and repository cleanup; resolved: the current cleanup grilling session means **Repository cleanup**.
