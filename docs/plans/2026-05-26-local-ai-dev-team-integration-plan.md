# Local AI Dev Team Integration Plan

Date: 2026-05-26
Status: READY FOR EXECUTION
Owner: Human-directed peer orchestrators

## Goal

Integrate peer orchestrators into the existing local AI dev team so Codex Desktop, VS Code/Copilot, and Antigravity can coordinate through devflow task ownership while local qwen worker subagents execute bounded jobs. Prove the integration with one end-to-end test project that exercises claim, preview, apply, verification, reporting, and handoff behavior.

## Current Baseline (Already True)

- devflow MVP safety loop is implemented and passing tests.
- Peer orchestrator model is documented in the coordination playbook.
- Local worker policy exists, with Ollama endpoint and baseline model guidance.
- Task lifecycle includes claim/release/status and run preview/apply split.

## Brainstormed Integration Options

### Option A: Human-Driven Relay (Fastest)

Use task files and git as the only integration surface. Each orchestrator reads and writes task/report files manually, and local models are invoked by the active orchestrator only.

Pros:
- zero new runtime complexity
- no additional service dependencies
- strongest alignment with current MVP contract

Cons:
- slower handoffs
- more human overhead for routing and triage

### Option B: Thin Local Dispatcher (Recommended)

Add a tiny dispatcher layer outside MVP execution path that standardizes local worker calls (model, timeout, retries, prompt envelope) while preserving task markdown + unified diff as canonical handoff artifacts.

Pros:
- faster and more consistent local worker execution
- keeps MVP deterministic (no direct provider calls in `devflow run`)
- clear foundation for post-MVP routing

Cons:
- requires adapter and health-check conventions
- introduces one more component to maintain

### Option C: Full Auto Router Now (Not Recommended Yet)

Implement role-based model/provider routing directly in execution flows immediately.

Pros:
- highest potential automation

Cons:
- conflicts with MVP guardrail that routing is post-MVP
- increases safety/debug surface before integration proof is complete

## Recommended Direction

Choose Option B: Thin Local Dispatcher, with strict boundaries.

Boundary rule:
- `devflow run` remains deterministic and model-agnostic.
- Dispatcher is used by orchestrators for worker jobs before task diff is committed to the task file.

## Target Architecture

1. Orchestrator layer:
- Codex Desktop, VS Code/Copilot, Antigravity
- each can claim and complete tasks end-to-end

2. Coordination layer:
- `.devflow/tasks/*.md` (canonical state)
- `.devflow/reports/*.report.md` (audit)
- git branch-per-task and clean-worktree gate

3. Worker layer:
- local dispatcher contract
- provider adapters (start with Ollama)
- bounded retries/timeouts

4. Verification layer:
- task commands, config commands, or auto-detect
- rollback and failure classification unchanged

## Integration Workstreams

### Workstream 1: Team Contract Normalization

- Keep one ownership grammar across all orchestrators:
  - `Assigned Agent`
  - `Owner Lock`
  - `Branch`
  - `Touched Files`
- Require claim before mutation of task file or touched scope.
- Require release or explicit transfer for handoff.

Acceptance:
- no parallel edits on claimed scope
- clear ownership in task headers and report metadata

### Workstream 2: Local Worker Connectivity Contract

Define one request/response shape for local jobs:
- request:
  - role (`planner|coder|reviewer|tester|summarizer`)
  - model
  - prompt
  - timeout_sec
  - retry_limit
- response:
  - output_text
  - duration_ms
  - attempt_count
  - success
  - error (if any)

Start adapter:
- Ollama at `http://127.0.0.1:11434`
- baseline model `qwen2.5-coder:1.5b`

VS Code orchestrator profile target:
- Copilot with GPT-5.5-high profile (or nearest available high-reasoning profile)

Acceptance:
- health check command succeeds before task execution
- timeout/retry behavior is deterministic and logged

### Workstream 3: Handoff + Audit Standard

- Every completed or failed task has a report.
- Reports include:
  - status transitions
  - safety decisions
  - verification outputs
  - rollback state
- Handoffs must reference task and report paths.

Acceptance:
- another orchestrator can continue from report + task file only

### Workstream 4: End-to-End Test Project (Integration Proving Ground)

Create one small, real project slice to prove collaboration:

Project name:
- `smoke-multi-agent-todo-cli`

Scope:
- add one CLI command + tests (small vertical slice)
- must touch source and tests
- must include at least one failed preview/apply iteration repaired by local worker

Execution path:
1. `devflow init` in clean temp repo/worktree.
2. Create task with ownership headers and unified diff payload placeholder.
3. Claim task as orchestrator A.
4. Use local worker adapter to draft patch.
5. Run `devflow run <task>` preview.
6. Inspect and commit preview metadata (or reset) to satisfy clean-worktree policy.
7. Run `devflow run <task> --yes` apply + verify.
8. If verification fails, classify and repair via worker loop; rerun.
9. Confirm COMPLETED status and report.
10. Hand off to orchestrator B for audit-only review.

Acceptance:
- preview/apply split is respected
- clean-worktree gate is observed
- rollback works on induced failure
- report is sufficient for peer audit

## Implementation Sequence (Next 48 Hours)

1. Lock integration contract docs (this plan + handoff + roadmap).
2. Add local worker health-check/runbook command set to docs.
3. Author test project task pack (`goal`, `plan`, `task`) under `.devflow/` examples.
4. Execute first end-to-end run with one orchestrator.
5. Execute peer audit handoff with second orchestrator.
6. Capture findings and convert into post-MVP routing backlog.

## Risks and Mitigations

- Risk: orchestration collisions across IDEs.
  - Mitigation: strict task claim ownership and touched-file declarations.

- Risk: local model instability or timeout.
  - Mitigation: bounded retries, explicit health checks, fallback to manual patch authoring.

- Risk: accidental drift toward in-run provider calls.
  - Mitigation: preserve rule that `devflow run` never calls providers in MVP.

## Definition of Done for Integration Planning

- one agreed integration architecture chosen (Option B)
- runbook for local agent connectivity documented
- one end-to-end test project spec ready and executable
- handoff and roadmap documents updated with this milestone
