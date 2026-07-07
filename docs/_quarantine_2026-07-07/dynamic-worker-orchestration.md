# Dynamic Worker Orchestration

Status: reference design. This is not the active MVP runtime contract. The current product supports shell workers plus evidence-only routing commands; dynamic task decomposition, non-shell adapters, autonomous worker assignment, and non-local execution require later registry and adapter-runtime promotion.

This document outlines the design for spawning, managing, and observing replaceable Worker Agents dynamically under the Dev-Flow control room. It maps out how high-level goals translate to isolated worker executions, how real-time feedback loops are recorded, and how human-in-the-loop questioning functions safely.

## Core Design Principles

To align with Dev-Flow boundaries, dynamic orchestration is designed around:
* **Local State:** Every step of task decomposition and execution preserves the local state as the source of truth.
* **Replaceable Workers:** Workers are dynamically allocated via adapters, keeping them highly modular and replaceable.
* **Human Approval:** No action of task promotion or branch integration can occur without human approval.
* **No Automatic Promotion:** Orchestration is strictly observation-centric; there is no automatic promotion of code changes.

---

## 1. Dynamic Task Decomposition

When the human developer proposes a broad goal, the Main Chat Agent decomposes it:

* **Slicing Goals:** Broad goals are broken down into small, standalone task packets (`TaskPacket`) representing isolated vertical slices.
* **Context Bundles:** Each task packet is provisioned with its own read-only subset of repository context, limiting the worker's focus and preventing context bloat.
* **Target Mapping:** Pre-defines exactly what files are allowed to be modified and what command verifies the change.
* **State Registration:** The task is registered in the control room kernel, creating `.devflow/tasks/<task_id>/task.yaml` and preparing `.devflow/workspaces/<task_id>/`.

---

## 2. Worker Allocation & Spawning

Future Dev-Flow supports multiple worker types through a standardized registry and adapter model:

* **Replaceable Worker Adapters:** Standardizes the runtime interface:
  ```text
  input: task + context + workspace + rules
  output: status + logs + questions + result + diff/changes
  ```
* **Shell Workers:** Executing local bash/sh commands or scripts directly in the sandbox workspace.
* **AI Coding Tools:** Wrapping external CLI developer tools (such as Claude Code, Aider, or Gemini CLI) as sub-processes, forcing their operations to run strictly inside the isolated workspace.
* **Spawning Lifecycle:** The Dev-Flow kernel handles shell execution, sets active environment variables, initiates timeouts, maps stdin/stdout, and tracks execution IDs.

---

## 3. Feedback & Observation Loop

To ensure complete visibility, the control plane captures real-time worker feedback:

* **Process Heartbeats:** Workers periodically update a lightweight task status or signal state to prevent silent hangs.
* **Append-Only Event Logs:** Every worker transition (e.g. `started`, `writing_file`, `executing_command`, `completed`, `failed`) is captured immediately as a JSON entry in `.devflow/tasks/<task_id>/events.jsonl`.
* **Output Redirection:** All console outputs (stdout/stderr) are captured and saved directly into `logs/worker.log` and `logs/verify.log` for auditable visibility.
* **Control Room Projection:** Derived summary indexes are compiled for the dashboard CLI, letting the human immediately see active runs, latest outputs, and errors.

---

## 4. Human-in-the-Loop Questioning (Q&A Loop)

Workers must never make assumptions or guess when faced with critical ambiguity. Instead, they pause and ask:

```text
 [Worker Agent] (Blocked)
        │
        ▼ 1. Writes to questions.jsonl
  [questions.jsonl]
        │
        ▼ 2. Kernel triggers Pause / status = "needs_human_input"
  [Dev-Flow Kernel]
        │
        ▼ 3. CLI Dashboard surfaces question
 [Human Developer]
        │
        ▼ 4. Records answer in CLI or task.yaml
  [Dev-Flow Kernel]
        │
        ▼ 5. Appends answer / status = "running"
 [Worker Agent] (Resumes with new context)
```

* **Structured Questions:** When a worker is blocked, it writes a structured question entry (containing the query, context, and potential choices) to `.devflow/tasks/<task_id>/questions.jsonl`.
* **Process Suspend:** The Dev-Flow kernel halts worker execution, captures current state, updates `task.yaml` status to `needs_human_input`, and alerts the human developer.
* **Human Resolution:** The human developer reviews the question via the CLI dashboard or terminal, and submits a clear answer.
* **Execution Resume:** The answer is saved back to the task's context model, the status returns to `running`, and the worker process is resumed or restarted with the newly supplied decision context, ensuring a durable history of design decisions.
