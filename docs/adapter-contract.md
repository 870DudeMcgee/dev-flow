# Worker Adapter Contract

Status: post-MVP design document.

This document defines the contract future worker adapters must follow. It uses the existing shell worker as the reference implementation and does not add runtime behavior beyond the current shell-worker control-room contract.

The broader future registry, provider, role, permission, adapter runtime, and routing architecture is defined in [docs/architecture/agent-registry-and-adapter-runtime.md](architecture/agent-registry-and-adapter-runtime.md). That document is the next design direction; this file remains the adapter safety contract.

Dev-Flow owns task state, workspace boundaries, verification evidence, and merge readiness. Worker adapters are replaceable execution engines that operate inside those boundaries.

## Runtime Maturity Boundary

Every known adapter is classified before it can be considered for task execution:

- `stable_runtime`: executable through `devflow task run`.
- `experimental_readonly`: may be described, inspected, packeted, or tested directly, but cannot execute through the task runner.
- `planned_not_executable`: design placeholder only; invoking it as a task worker must fail clearly.

Only `shell` and `manual` are `stable_runtime` adapters in the current milestone. Provider-backed adapters remain non-executable until a future slice promotes them with explicit tests, threat modeling, enable flags, and updated docs.

## Reference Adapter: Shell Worker

The shell worker is the current reference adapter because it is the only automated execution path in the MVP. The manual proof-agent is also stable-runtime, but it generates bounded human handoff evidence rather than provider-backed execution.

### What It Reads

The current shell-worker path is invoked by Dev-Flow. Dev-Flow reads canonical task artifacts, validates the workspace, and passes a bounded execution input to the adapter. The shell command itself receives the isolated workspace as its current working directory and reads files available there.

The reference path is grounded in these readable surfaces:

- `.devflow/tasks/<task-id>/task.yaml` for canonical task identity, title, status, workspace path, timestamps, and current state.
- `.devflow/tasks/<task-id>/summary.json` when present, as optional derived/cache state only.
- `.devflow/tasks/<task-id>/events.jsonl` as append-only task history and evidence.
- `.devflow/workspaces/<task-id>/` as the isolated task workspace and only execution directory.
- Explicit artifacts that Dev-Flow chooses to expose to the worker.

### What Workspace It Receives

The shell worker receives `.devflow/workspaces/<task-id>/` as its process working directory. The worker command executes from that directory and should treat it as the whole writable jobsite for the task.

The main checkout is not the worker workspace. A worker may inspect only the files Dev-Flow has placed in, copied into, or explicitly exposed from the isolated workspace.

### What It Writes

- Raw worker command output to `.devflow/tasks/<task-id>/logs/worker.log`, captured by Dev-Flow.
- Result files and other task artifacts created by the command inside `.devflow/workspaces/<task-id>/`.
- A Dev-Flow-owned result summary at `.devflow/tasks/<task-id>/result.md`.
- Structured result/report artifacts only when Dev-Flow defines and exposes an approved path for them.

### What Events, Logs, And Results It Leaves Behind

The shell worker leaves evidence through Dev-Flow-owned files:

- `logs/worker.log` records command stdout, stderr, and execution evidence captured by Dev-Flow.
- `events.jsonl` records lifecycle events appended by Dev-Flow.
- workspace files under `.devflow/workspaces/<task-id>/` are the worker's result artifacts.
- `result.md` records Dev-Flow's summary of the worker run.
- `task.yaml` records the canonical state chosen by Dev-Flow after execution.

### What It Cannot Do

The shell worker cannot:

- mutate the main checkout directly;
- choose or overwrite canonical task state outside Dev-Flow's state transition rules;
- mark verification as passed or failed;
- mark work merge-ready;
- promote, copy back, merge, or open pull requests;
- bypass human approval gates;
- depend on `summary.json` as source of truth.

## Adapter Read Contract

Future adapters may read only the task context Dev-Flow exposes. The stable read surfaces are:

- `task.yaml`: canonical current task state. If any other artifact disagrees with `task.yaml`, the canonical task file wins.
- `summary.json`: optional derived/cache state for visibility and token efficiency. It may be missing, stale, malformed, deleted, or regenerated without losing information.
- `events.jsonl`: append-only history and evidence. Adapters may use it to reconstruct what happened, but they must not treat it as an editable state store.
- `.devflow/workspaces/<task-id>/`: isolated workspace contents for the assigned task.
- explicit Dev-Flow artifacts: files or directories Dev-Flow intentionally exposes to the adapter for a task.

Adapters must not infer permission to read unrelated repository paths from local filesystem access alone. Visibility is controlled by the task workspace and explicit Dev-Flow exposure.

The minimal future read packet for adapters is described in [task-packet-contract.md](task-packet-contract.md).

## Adapter Write Contract

Future adapters may write only through approved task surfaces:

- worker log output captured by Dev-Flow into `.devflow/tasks/<task-id>/logs/worker.log` or a future adapter-specific log owned by Dev-Flow;
- result artifacts inside `.devflow/workspaces/<task-id>/`;
- structured questions, if introduced later, through a Dev-Flow-owned question artifact or API;
- task events only through Dev-Flow-owned APIs or approved files.

Adapters must not write directly to canonical state files unless Dev-Flow explicitly owns and validates that write path. In particular, adapters must not treat `task.yaml`, `verification.json`, or merge-readiness artifacts as free-form output files.

## Adapter Must-Never-Bypass Rules

Adapters must never bypass these ownership boundaries:

- Workspace containment: task work happens inside `.devflow/workspaces/<task-id>/` unless Dev-Flow explicitly exposes an artifact.
- Task state ownership: Dev-Flow owns `task.yaml`, state transitions, task ownership, and lifecycle events.
- Verification ownership: Dev-Flow runs verification and owns verification state.
- Merge readiness ownership: Dev-Flow decides whether evidence is sufficient to present work for human review.
- Main checkout protection: workers do not mutate the main checkout directly.
- Human approval gates: workers do not promote, copy back, merge, or submit work without human-approved Dev-Flow flow.
- Canonical file authority: `task.yaml`, `events.jsonl`, `verification.json`, and logs remain the evidence hierarchy; derived caches never override canonical files.

## Verification Ownership

Workers may suggest verification commands, produce candidate output, or write notes about how their work should be checked. Workers do not run authoritative verification for Dev-Flow state.

Dev-Flow:

- runs verification commands from `.devflow/workspaces/<task-id>/`;
- captures verification output in `.devflow/tasks/<task-id>/logs/verify.log`;
- writes `.devflow/tasks/<task-id>/verification.json`;
- decides `verified` and `verification_failed` states.

This keeps verification evidence separate from worker claims. A worker can say "I think this passes"; Dev-Flow decides whether it actually passed.

## Merge Readiness Ownership

Workers never mark work merge-ready directly.

Dev-Flow evaluates merge readiness from:

- canonical task state;
- verification evidence;
- workspace status and result artifacts;
- future review gates, if added later.

Human approval remains required before any promotion, copy-back, pull request, or merge behavior. Merge readiness is a control-room decision, not a worker self-certification.

## Future Adapter Examples

These examples describe possible future adapters. They are explicitly not implemented by this document:

- Codex adapter: a worker adapter that would run a Codex-based coding tool inside the task boundary. The smallest future slice is sketched in [codex-adapter-brief.md](codex-adapter-brief.md).
- Local model adapter: a worker adapter that would run a local model or local coding assistant inside the task boundary.
- IDE adapter: a worker adapter that would coordinate an IDE-driven agent while preserving Dev-Flow state ownership.
- Remote worker adapter: a worker adapter that would execute outside the local process while reporting through approved Dev-Flow artifacts or APIs.

Any future adapter must satisfy this contract before it can participate in task state, verification, or merge-readiness flows.

## Out Of Scope

This document does not define or implement:

- provider-specific implementation;
- agent registry loading or routing implementation;
- multi-agent orchestration;
- copy-back;
- merge automation;
- PR automation;
- dashboard expansion;
- database state;
- worktrees;
- memory systems;
- DAG systems;
- trace systems;
- eval systems.
