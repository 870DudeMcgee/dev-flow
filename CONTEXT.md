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

### Local model server

A resident local model process or endpoint that may serve model responses but has no task authority by itself.

### Worker profile

A named model, capability, and permission identity that can be selected by an execution surface but is not itself proof of readiness or completion.

### Execution surface

An approved Dev-Flow, Hermes, or Codex path that can consume a bounded packet and produce evidence under explicit authority limits.

### Local worker

An approved local model route acting through an execution surface to produce bounded task evidence.

### Fleet telemetry

Read-only evidence about whether local model lanes are configured, listening, loaded, smoke-proven, or mismatched.

### Review queue

The operator-facing list of tasks that need verification, review, human decision, or promotion action.

### Evidence stream

The operator-facing timeline or list of concrete task artifacts: events, logs, worker output, verification records, promotion previews, and other review evidence.

### Next safe action

The most useful action Dev-Flow can recommend without hiding safety requirements. It must name the task or project, expose the exact command when applicable, and make human approval requirements visible.

### Task workbench

The operator-facing projection that turns task state into the first usable work surface: selected task, Worker lanes, Review queue, Evidence stream, task controls, gate progress, worker/model identity, and next safe actions.

The Task workbench is not canonical state. It is a derived read model for usability and should remain backed by existing task artifacts, worker evidence, verification artifacts, and promotion readiness evidence.

### Context Map

A proposed standalone read-only codebase orientation tool that answers "where should I look, and why?" for a codebase task by combining current source indexes, Graphify evidence, `CODE_MAP.md`, active docs, and selected Obsidian memory notes.

Context Map may later expose an MCP server for Codex, Hermes, Dev-Flow, or other clients. It is not execution authority. It must not edit source, route workers, verify readiness, promote work, or silently write durable vault notes.

## Relationships

- A **Local model server** can support one or more **Worker profiles**.
- A **Worker profile** becomes a **Local worker** only through an **Execution surface**.
- A **Local worker** produces evidence for a **Task**; Dev-Flow verification decides readiness, closure, and promotion.
- **Fleet telemetry** describes local model availability; it is not task evidence or verification proof by itself.
- A **Context Map** can orient a worker before source inspection, but live source, tests, docs, and Dev-Flow verification still decide whether a change is correct.

### Repository cleanup

A source-tree hygiene activity that classifies repository material before changing, archiving, untracking, or deleting it.

Repository cleanup candidates are classified as active product, compatibility bridge, generated/local runtime state, historical reference, future roadmap, stale context candidate, or stale artifact.

### Stale context candidate

A document or reference whose current accuracy is untrusted until reconciled against active product intent, code, tests, live Dev-Flow behavior, and fresh architecture evidence.

## Flagged ambiguities

- "cleanup" was used to mean both task-owned runtime cleanup and repository cleanup; resolved: the current cleanup grilling session means **Repository cleanup**.
- "local worker" was used to mean a model server, provider, profile, or runtime path; resolved: a **Local worker** is only an approved local model route acting through an **Execution surface**.
