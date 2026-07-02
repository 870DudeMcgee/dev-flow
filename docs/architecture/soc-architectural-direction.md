# SOC Architectural Direction (Scout-Orchestrator-Coder)

This document defines the overarching architectural strategy for DevFlow and its interaction with Hermes agents. It moves away from "multi-agent" complexity toward a **Plane-based Architecture** that separates planning, context gathering, and execution into distinct domains.

## 1. The Four Planes of DevFlow

The system is organized into four distinct planes to minimize context-overhead while maximizing reasoning depth on complex software tasks.

| Plane | Category | Primary Role | Ownership | Interaction Model |
| :--- | :--- | :--- | :--- | :--- |
| **Control** | Planning | The Orchestrator | High-Reasoning | Defines "Why". Breaks goals into tasks. |
| **Scout** | Discovery | Context Compression | Analytical/Read-Only | Identifies "Where" and "How much." |
| **Execution** | Implementation | The Coder | Focused Execution | Executes the plan in isolated workspaces. |
| **Memory** | Retention | State & Knowledge | Human + Agent | Persists intent, history, and context-free facts. |

## 2. Role Definitions

### The Orchestrator (Control Plane)
*   **Identity:** High-reasoning model with high-level system knowledge.
*   **Focus:** Task decomposition, priority weighting, contradiction detection, and loop selection.
*   **Constraint:** **Must not perform manual repository spelunking.** It relies on the Scout for context. Its primary output is a set of verified plans and specific task bounds for Coder agents.

### The Scout (Scout Plane)
*   **Identity:** Lightweight, fast-acting agents/scripts focused on graph analysis and dependency mapping.
*   **Focus:** Identifying blast radius, finding entry points, identifying test coverage, and extracting "Architectural Facts."
*   **Output:** **Dense Context Packets**. Scouts never write code; they provide the "scaffolding" of knowledge that allows the Orchestrator to see the entire repository without consuming context windows.

### The Coder (Execution Plane)
*   **Identity:** Focused, implementation-centric experts.
*   **Focus:** Editing files, refactoring modules, and writing tests within a bounded scope.
*   **Constraint:** **Atomic Execution.** They receive a "Job Description" that includes exactly which files to touch and what 0-success metrics (tests) must be met.

## 3. The Dense Context Packet (Contract)

To ensure the Orchestrator can act on Scout data without being overwhelmed, every Scout output must adhere to a compressed schema:

```json
{
  "objective": "Clear description of what is being found",
  "confidence": "Scout's confidence score (0.0-1.0)",
  "architectural_slice": {
    "entrypoints": ["file paths"],
    "core_symbols": ["Function/Class names"],
    "upstream_dependencies": ["Who calls this?"],
    "downstream_impact": ["What does this affect?"]
  },
  "evidence": [
    { "path": "...", "lines": "...", "reason": "..." }
  ],
  "constraints": {
    "repo_rules": [],
    "non_goals": []
  },
  "risk_map": ["List of possible side-effects"],
  "recommended_next_action": {
    "role": "coder/reviewer/researcher",
    "scope": "...",
    "why": "..."
  }
}
```

## 4. Safety and Isolation Boundaries

*   **Worktree Isolation:** Every Execution task is performed in a dedicated `git worktree`. This prevents cross-agent collisions on the same branch.
*   **Sandbox Enforcement:** Where possible, execution should occur within a containerized terminal backend (e.g., Docker) to isolate filesystem changes from the host machine.
*   **Zero-Implicit Trust:** No agent—including Scouts—is permitted wide-write access or secret-access unless explicitly required by a specific, human-approved task.

## 5. The Memory Strategy

We separate "How we do things" (Rules) from "Who we are" (Identity).

*   **AGENTS.md:** Project-specific architectural boundaries, commands, and critical implementation rules.
*   **DevFlow Task State:** Active session-level task definitions, loop progress, and intermediate planning artifacts.
*   **Obsidian:** The durable **Knowledge Base**. This stores research breakthroughs, long-term architecture decisions, and the "Project Manual." It is the source of truth for high-level intent.
*   **Hermes Memory (Skills/Mem):** Localized agent behavior, shortcuts, and conversational context.

## 6. Operational Flow Example

1.  **User Request:** "Make the auth timeout configurable in the config file."
2.  **Orchestrator Analysis:** Breaks this into a research phase.
3.  **Scout Activation:** Identifies where `auth` is handled (middle-ware vs controller) and which tests cover it.
4.  **Dense Packet Return:** "Auth is in `src/middleware`. Impact involves 2 existing test files."
5.  **Orchestrator Planning:** Writes the plan.
6.  **Coder Execution:** Identifies the specific lines to change and applies a patch, verifying against those tests.
7.  **Audit & Memory:** Update the Task State and report back to the user.
```bash
# Verification: Ensure this file is accessible from the project root
ls docs/architecture/soc-architectural-direction.md
```
