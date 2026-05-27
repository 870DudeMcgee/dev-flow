# Implementation Plan: Agentic Orchestrator (Devflow + Superpowers-First)

## Goal
Build an orchestrator that always starts with `/using-superpowers`, selects the right process/implementation skills, plans before coding, and dispatches as many local AIs as possible for parallel work—strictly following Devflow.

## Task Breakdown (Parallelizable)

### 1. Orchestrator Entry Logic
- Implement entrypoint that receives user prompt and always invokes `/using-superpowers`.
- File: likely `src/devflow/orchestrator.py` (or similar).

### 2. Process Skill Selection
- Implement logic to select and invoke the correct process skill (brainstorming, grill-me, doc-coauthoring) based on prompt ambiguity.
- File: orchestrator module.

### 3. Implementation Skill Selection
- Implement logic to select the correct implementation skill (tdd, subagent-driven-development, etc.) after process skill.
- File: orchestrator module.

### 4. Plan Generation
- Implement plan-writing logic using `/writing-plans` skill.
- Ensure plan is actionable, parallelizable, and includes file/context scope and verification steps.
- File: orchestrator module.

### 5. Parallel Agent Dispatch
- Implement logic to:
  - Detect parallelizable tasks in the plan.
  - Spin up as many local AI agents as hardware allows.
  - Assign each agent a distinct, non-overlapping task.
  - Aggregate and coordinate results.
- File: orchestrator module, possibly new agent manager.

### 6. Devflow Workflow Enforcement
- Implement enforcement of PLAN → CONTEXT → TEST → IMPLEMENT → VERIFY → REVIEW → REPORT for each subtask and overall goal.
- File: orchestrator module.

### 7. User Interaction Layer
- Implement logic to:
  - Surface blockers, ambiguities, or required approvals to the user.
  - Show status, diffs, and results.
  - Never require manual packet or agent management.
- File: orchestrator module, UI layer if applicable.

### 8. Extensibility & Config
- Ensure orchestrator is extensible for new skills and workflows.
- File: orchestrator module, config files.

## File/Context Scope
- Main implementation: `src/devflow/orchestrator.py` (or equivalent new file).
- May touch: agent manager, skill registry, UI layer (if present), config files.

## Verification Steps
- Unit tests for orchestrator logic (parallel dispatch, skill selection, workflow enforcement).
- Integration test: Simulate user prompt, verify full workflow is followed, parallel agents are dispatched, and result matches user intent.
- Manual test: Run orchestrator with various prompts, confirm agentic UX and parallelism.

## Parallelization
- Tasks 1–4 can be developed in parallel as stubs, then integrated.
- Task 5 (parallel agent dispatch) can be developed and tested independently.
- Task 6 (workflow enforcement) can be layered on after initial integration.
- Task 7 (user interaction) can be developed in parallel with core logic.

## Success Criteria
- Orchestrator always starts with `/using-superpowers`.
- Process and implementation skills are selected in correct order.
- Plan is written before any code is generated.
- All parallelizable tasks are dispatched to local AIs.
- Devflow workflow is strictly enforced.
- User only sees status, blockers, and results—never manual management.
