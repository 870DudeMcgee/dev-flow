# Ollama Supervisor Loop Design

Status: superseded as next-priority architecture. This document is retained as historical design context for shell-supervised local Ollama experiments. Future Ollama work must follow [docs/architecture/agent-registry-and-adapter-runtime.md](../../architecture/agent-registry-and-adapter-runtime.md): registry loading, manual adapter, shell alignment, then local adapter implementation.

## Decision

Dev-Flow should become operational for local workers without introducing direct provider wiring, a Codex agent, autonomous router, complex scheduler, web dashboard, or legacy workflow machinery.

Ollama workers should run as task-scoped shell commands managed by the existing control-room contract. The supervisor loop is a small launcher and observer around task state, not a new autonomous orchestration framework.

## Goals

- Run local Ollama workers through task-specific control-room folders.
- Preserve the existing `.devflow/tasks/<task_id>/` state model and `.devflow/workspaces/<task_id>/` edit isolation.
- Keep the CLI dashboard as the operational visibility surface.
- Make worker execution auditable through existing logs, events, verification records, and result artifacts.
- Avoid direct provider execution before the registry/manual/shell-alignment sequence exists.

## Non-Goals

- No Codex agent.
- No dependency graph scheduler.
- No autonomous routing.
- No browser or web dashboard.
- No automatic commit, push, merge, PR creation, or promotion.
- No revival of legacy task files, memory, DAGs, traces, or patch gates.

## Task-Scoped Ollama Execution

Each Ollama run belongs to one task id.

The task folder remains the control envelope:

```text
.devflow/tasks/<task_id>/
  task.yaml
  events.jsonl
  questions.jsonl
  result.md
  packet.json
  logs/
    worker.log
    verify.log
```

The workspace remains the edit sandbox:

```text
.devflow/workspaces/<task_id>/
```

The supervisor should pass both paths to the worker command:

```text
DEVFLOW_TASK_ID=<task_id>
DEVFLOW_TASK_DIR=.devflow/tasks/<task_id>
DEVFLOW_WORKSPACE=.devflow/workspaces/<task_id>
```

The Ollama process may read prompts and write reports/questions under the task folder. Any repo file edits must happen under the workspace so promotion and verification stay coherent.

## Minimal Supervisor Loop

The first loop should be intentionally small:

```bash
devflow supervise --once
devflow supervise --task <task_id> --once
```

Behavior:

1. Read canonical task records.
2. Select tasks in a runnable state such as `created`.
3. Skip tasks already `running`, `verified`, `verification_failed`, `failed`, or `blocked`.
4. Build or refresh the task packet.
5. Launch an Ollama shell command through the existing shell-worker runner.
6. Record normal worker logs and events.
7. Leave verification and promotion explicit.

Parallel execution can wait. If added later, it should be a simple `--max-parallel N` cap, not dependency scheduling.

## Worker Command Shape

The implementation should start with a configurable shell command instead of a new adapter class.

Example:

```bash
devflow supervise --task task-0001 --once --worker-command scripts/run-ollama-task
```

The launcher receives the task id and paths through environment variables. It can invoke `ollama run <model>` internally and write a handoff to `result.md`.

## Operational Definition

Dev-Flow is operational for this slice when a human can:

1. Create multiple tasks.
2. Run one or more Ollama shell workers against their task-specific control envelopes.
3. See progress and outcomes in `devflow dashboard`, `devflow task show`, and `devflow task log`.
4. Run explicit verification.
5. Preview and promote verified workspace changes.

CLI dashboard visibility is sufficient for this milestone.

## Risks

- Running the worker with the task folder as the edit working directory would bypass existing workspace promotion semantics. The task folder should hold control artifacts; the workspace should hold repo edits.
- A supervisor loop can become a scheduler by accident. Keep the first version to explicit task selection and `--once`.
- Local Ollama execution must be folded into the registry and adapter-runtime architecture before it becomes an active non-shell adapter.
