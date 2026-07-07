# Subskill: Role-Bounded Context Selection

This subskill governs bounding your active context depending on your current agent role.

## Guidelines

Select the appropriate bounded context profile based on your role in this slice:

### 1. Planner Role
* **Context Limit**: [docs/DEVFLOW_SOURCE_OF_TRUTH.md](docs/DEVFLOW_SOURCE_OF_TRUTH.md), `docs/README.md`, `task.yaml`, and git diff.
* **Discipline**: Focus purely on feasibility, slice size, and planning. Avoid reading codebase files or writing code.

### 2. Writer / Implementer Role
* **Context Limit**: Touched implementation files, directly related tests, and the approved plan.
* **Discipline**: Run only necessary tests. Keep files open only if they require edits. Do not read legacy archive docs or distant packages.

### 3. Reviewer Role
* **Context Limit**: Plan, code diffs, `verification.json`, and verification log.
* **Discipline**: Do not modify files. Conduct review-only inspections of code correctness and risk mitigations.

### 4. Debugger / Repair Role
* **Context Limit**: Touched files, failing test file, and raw traceback log.
* **Discipline**: Identify exact line failure. Write minimal fixes. Avoid rewriting working architecture.
