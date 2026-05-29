# DevMode / Dev-Flow Boundary

## Summary

This document defines the conceptual and operational boundary between DevMode and Dev-Flow. Establishing a clear separation prevents architectural drift and ensures that discipline rules do not become conflated with the runtime control-plane platform.

The core guiding principle is:

```text
DevMode tells agents how to behave.
Dev-Flow gives agents safe places to work and records what happened.
```

---

## DevMode Owns

DevMode is the **discipline layer** for agent behavior. It is a portable set of rules, modes, and skills that enforce rigorous engineering practices on the agent itself.

DevMode owns:

* **Agent Discipline:** The Four Iron Laws and mode-gating behavior.
* **Operational Modes:** Distinguishing between read-only (investigative) and active (implementation) operations.
* **Specialized Skills:** Composed instruction guides for TDD, systematic debugging, token budgeting, etc.
* **Harness Integrations:** Instructions tailored for specific IDE interfaces (e.g., Cursor, Claude Code, Gemini CLI).
* **Verification Behavior Guidance:** Instructing the agent on why and how to seek verification before claiming completion.
* **Handoff Formats:** The standard layout of task-completion reports and workspace transfers.

---

## Dev-Flow Owns

Dev-Flow is the **orchestration and control-room system**. It is a local-first platform that provides structure, isolation, process scheduling, and visibility for parallel workers.

Dev-Flow owns:

* **Task State:** Canonical records (like `task.yaml` and `events.jsonl`) that capture task parameters and progress.
* **Filesystem Artifacts:** Bounded task directories containing logs, questions, and verification metadata.
* **Isolated Workspaces:** Provisioning physical directory copies (or future worktrees) where code mutation is quarantined.
* **Worker Lifecycle:** Creating, launching, and managing the execution processes of workers (e.g., shell scripts, Aider, Hermes).
* **Logs & Visibility:** Capturing append-only stdout/stderr for both worker execution and verification commands.
* **Q&A Interface:** Surfacing structured blocking questions from workers to the human controller and persisting answers.
* **Verification Execution:** Executing test and assertion commands within isolated sandboxes.
* **Readiness State:** Determining if a task meets the strict criteria to be marked `verified` or review-ready.
* **Promotion/Merge Gates:** Enforcing human review and controlled integration before scratchpad changes reach the main branch.

---

## How They Work Together

DevMode and Dev-Flow form a symbiotic developer environment. 

1. **A Safe Environment:** Dev-Flow provisions an isolated scratchpad workspace for a specific task.
2. **Discipline at Work:** The worker agent enters the workspace, guided by DevMode's rules (e.g., writing failing tests first via the TDD skill, respecting token constraints).
3. **Continuous Observation:** As the worker executes tasks, the Dev-Flow kernel captures execution metrics and terminal logs, making them visible to the human.
4. **Authoritative Evidence:** When the worker claims completion, Dev-Flow runs the configured verification commands. The outcome is recorded by Dev-Flow as objective proof of readiness.
5. **Read-Only Coordination:** The Main Chat agent, operating under DevMode's read-only planning/review discipline, inspects the Dev-Flow task artifacts, reviews the verification logs, and summarizes status for the human's final approval.

---

## Anti-Patterns

To keep both systems clean, avoid these common design traps:

* **Making DevMode a runtime orchestrator:** DevMode should never spawn background processes, manage task directories, or mutate task files directly. It is an instruction set, not a runtime daemon.
* **Making Dev-Flow a prompt pack:** Dev-Flow's source code should not consist of agent system prompts, framing templates, or general reasoning hacks. It must be an operational kernel built in Python.
* **Letting the main chat mutate repo files directly:** The main coordinator agent must not stage, commit, edit, or push files under the main checkout. All mutating work belongs inside Dev-Flow's isolated task workspaces.
* **Treating AI memory as the source of truth:** Neither DevMode nor Dev-Flow should rely on hidden chat history or vector-db memory. Important facts must be recorded as durable filesystem artifacts.
* **Worker merging directly to main:** Worker processes must never merge branches or apply changes directly to the main checkout. Humans control promotion gates.
* **Duplicating DevMode skill content inside Dev-Flow docs:** Keep Dev-Flow docs focused on task state, command behavior, CLI, and APIs. Dev-Flow does not need to document TDD or systematic debugging.

---

## Correct Integration Pattern

When Dev-Flow runs a worker, it provides:
1. An isolated workspace directory.
2. A task packet (`TaskPacket`) containing files allowed to be changed and metadata.
3. Access to DevMode's rules and skills so the worker is instructed to operate with high discipline inside that workspace.

Dev-Flow records the worker's output and verification outcome, which are then used by the Main Chat agent (following DevMode's read-only review discipline) to assist the human.

---

## Current MVP Rule

For the Milestone 1 Shell-Worker control room, the boundary is absolute:

* Dev-Flow's CLI, task commands, filesystem artifacts, and safety rules remain 100% focused on shell worker execution and plain-text logging.
* Dev-Flow may reference DevMode's standard handoff or verification principles in its output, but Dev-Flow does not contain or run DevMode skill rules within its own runtime code.
