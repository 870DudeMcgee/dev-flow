# Dev-Flow Worker Adapter Specification

Status: historical/reference design. The active MVP contract is [mvp-contract.md](mvp-contract.md); the current adapter safety boundary is [adapter-contract.md](adapter-contract.md); the next registry/provider/role architecture is [docs/architecture/agent-registry-and-adapter-runtime.md](architecture/agent-registry-and-adapter-runtime.md). This document must not be used to expand runtime behavior beyond the shell-worker control room.

## 1. Core Principle: Replaceable Intelligence, Sacred State

In the Dev-Flow ecosystem, **workers are replaceable execution engines**. Coding intelligence—whether it is a simple shell runner, a local LLM, or a state-of-the-art agent like Aider or Claude Code—is decoupled from the control plane. 

**Dev-Flow owns the control room**:
* **State Management**: Enforcing the task lifecycle.
* **Verification**: Running independent verification tests.
* **Promotion**: Human-controlled, path-constrained synchronization to the main checkout.

The worker adapter boundary ensures that intelligence operates safely within strict limits without any process authority over the project's codebase.

---

## 2. The Worker Adapter Role

A Dev-Flow Worker Adapter:
1. **Operates strictly inside an isolated task workspace** (`.devflow/workspaces/<task_id>/`).
2. **Receives bounded task context** and instructions only.
3. **Writes logs, results, and questions** strictly through Dev-Flow-approved paths.
4. **Does not mutate canonical state directly** (except through specified allowed outputs).
5. **Never promotes, stashes, stages, commits, merges, or pushes changes** to the main repository.

---

## 3. Contract Boundaries

### 3.1 Adapter Inputs
At invocation, the adapter receives:
* **Task ID**: Deterministic identifier (e.g. `task-0001`).
* **Workspace Path**: The path to the copied sandbox directory.
* **Task Instructions**: The user's prompt or title describing the task.
* **TaskPacket Projection** (e.g., `packet.json`): A deterministic, virtualized, secret-redacted JSON context bundle.
* **Allowed Artifact Paths**: Predefined log, results, and question file paths.
* **Environment Constraints**: Execution timeouts and directory boundaries.

### 3.2 Adapter Outputs
Upon completion or blockage, the adapter yields:
* **Worker Log Evidence** (`logs/worker.log`): Raw terminal execution logs.
* **Result Summary** (`result.md`): A markdown-formatted summary of what was changed.
* **Questions** (`questions.jsonl`): Structured questions to prompt human input when blocked.
* **Execution Outcome**: Status signal (`complete`, `worker_failed`, `timeout`) and exit code.

---

## 4. State & Boundary Separation

To preserve state integrity, the filesystem is partitioned into strict categories:

| File Type | Canonical State (Dev-Flow Authority) | Derived/Non-Canonical (Cache/Worker Writes) |
| :--- | :--- | :--- |
| **State Files** | `task.yaml` (lifecycle state)<br>`events.jsonl` (history)<br>`verification.json` (authoritative verification results) | `summary.json` (cached presentation view)<br>`packet.json` (generated TaskPacket projection) |
| **Worker Files** | `questions.jsonl` (canonical blocks/answers) | `result.md` (markdown summary)<br>`logs/worker.log` (execution stdout/stderr) |

---

## 5. Forbidden Adapter Behavior

No adapter may ever:
* **Write to the main checkout**: All file changes must be written strictly inside `.devflow/workspaces/<task_id>/`.
* **Perform Git workflow automation**: No staging, committing, branching, merging, or PR creation.
* **Introduce databases**: Rely strictly on flat filesystem structures; do not add SQLite, PostgreSQL, or vector DB dependencies.
* **Own routing decisions**: Keep execution model-agnostic; no built-in LLM gateway scheduling or pricing logic.
* **Use hidden memory as authority**: Task context must remain completely inspectable in files (`events.jsonl`, `questions.jsonl`), not in invisible memory caches.

---

## 6. Supported Worker Profiles (Reference & Future)

Adapters can wrap any programming agent or command. The following profiles are non-binding examples:

1. **Shell Worker (The Reference Adapter)**:
   * Runs local shell subprocesses inside the sandbox workspace.
   * Leverages basic exit codes and timeout monitoring.
2. **Codex CLI Adapter**:
   * Bridges to Codex's localized code generation services.
3. **Aider / Claude Code Adapters**:
   * Wraps interactive CLI agents in non-interactive modes, capturing their git-like workspace modifications and output logs.
4. **Local LLM Worker**:
   * Interfaces with local llama.cpp or Ollama endpoints to carry out simple code-generation scripts.

---

## 7. Next Phase: First Non-Shell Slice Guidance

When the first non-shell adapter is scheduled:
* **Registry First**: Implement durable agent/provider/role loading before direct provider calls.
* **Manual Before Remote**: Prove manual packet handoff and shell alignment before local or remote model adapters.
* **Default Status**: The reference `shell` adapter must remain the default worker type.
* **Acceptance Requirement**: The new non-shell adapter must strictly pass the verification gauntlet, demonstrating that:
  1. It reads only virtualized `TaskPacket` projections.
  2. It writes only within its sandbox workspace.
  3. It correctly routes raw logs to `worker.log` and questions to `questions.jsonl`.
  4. It submits itself unconditionally to Dev-Flow's authoritative verification step.
