# Dev-Flow: Unified Control-Loop Architecture

Status: reference architecture. This document describes the longer-term control-loop shape and is not the active runtime contract. For current implementation authority, use [mvp-contract.md](mvp-contract.md) and [control-room-mvp.md](control-room-mvp.md).

Dev-Flow is a local-first, filesystem-backed control room for AI software development.

It is not a coding agent.
It is not a model wrapper.
It is not a prompt framework.
It is not a chat workflow.

It is the durable control layer that lets replaceable AI workers build software through bounded tasks, isolated workspaces, visible state, verification, and human-controlled promotion.

## 1. Core Philosophy

AI workers are unreliable when they are treated as the source of truth. They become useful when surrounded by durable filesystem state, explicit goals, bounded task packets, permissioned workspaces, append-only evidence, verification gates, retry/escalation rules, and human promotion authority.

Dev-Flow does not try to make models perfect. Dev-Flow makes imperfect models useful.

### Mantra
- Agents are replaceable.
- State is sacred.
- Visibility is mandatory.
- Isolation comes before autonomy.
- Verification belongs to Dev-Flow.
- Humans control promotion to main.

### The PLC Analogy
Dev-Flow operates as a PLC-style control loop for AI software labor.

```
+---------------------------------------+
|          PLC Control Loop             |
|                                       |
|  1. Read Inputs                       |
|     (Repo state, tasks, logs, tests)  |
|               |                       |
|               v                       |
|  2. Evaluate Logic                    |
|     (Goal criteria, state machines)   |
|               |                       |
|               v                       |
|  3. Set Outputs                       |
|     (Task creation, worker runs, Qs)  |
|               |                       |
|               +-----------------------+
|               | Repeat                |
+---------------+-----------------------+
```

- **PLC inputs**: Repo state, task files, logs, verification results, human instructions.
- **PLC logic**: Goal criteria, state machines, permission rules, retry rules.
- **PLC outputs**: Task creation, worker assignment, verification, human questions.
- **PLC memory**: Filesystem artifacts.
- **PLC actuators**: Local models, cloud models, shell workers, IDE agents.
- **PLC sensors**: Tests, diffs, logs, status files.
- **PLC interlocks**: Locks, isolated workspaces, no auto-merge, human approval.
- **PLC setpoint**: Explicit success criteria.

The model is not the controller. The model is an actuator. Dev-Flow is the controller.

### Filesystem as Context
Instead of stuffing the entire codebase and history into a model's context window, Dev-Flow stores durable context on disk and feeds only a bounded working slice to the worker:

- **Filesystem** = long-term memory
- **Task packet** = short-term working context
- **Worker** = bounded executor
- **Verification** = truth signal
- **Human** = promotion authority

This is what makes weaker local models useful: a local model does not need to understand the whole system, only perform one constrained job against one bounded packet.

---

## 2. Canonical Authority Hierarchy

Dev-Flow clearly distinguishes authoritative truth from mere evidence:

1. **Human instruction**: Ultimate source of intent.
2. **Canonical Dev-Flow state files**: Autoritative state on disk (`goal.yaml`, `task.yaml`).
3. **Latest verification artifact**: Autoritative verification summary (`verification.json`).
4. **Append-only events**: Durable evidence (`events.jsonl`, `questions.jsonl`).
5. **Worker reports**: Non-canonical worker claims (`worker-report.md`).
6. **Summaries/caches**: Derived files for performance or convenience (`summary.json`).

*Rule:* A model or worker may propose changes, but never silently change canonical truth. A worker report may claim completion, but cannot mark a task complete by itself.

---

## 3. Canonical Filesystem/Context Structure

Define the intended Dev-Flow filesystem structure in enough detail that both humans and workers can tell where state, context, history, and decisions belong.

Core idea:

Dev-Flow's filesystem is not a dumping ground. It is the durable context layer. Each level should contain only the information relevant to that level, and the structure should make the next safe action obvious without requiring a model to reread the entire project.

This structure defines both runtime state and living project context. It must not be flattened into generic `docs/`, workflows, or `AGENTS.md` discipline. The nested `.devflow/` structure is the core product model.

This is the intended durable structure for the control room. The current shell-worker control-room contract may implement a smaller runtime subset, but new filesystem work should move toward this shape unless a newer active contract explicitly supersedes it.

The seed template for this generated structure lives in `src/devflow/control_room/seed.py`. `devflow init` materializes `.devflow/` locally; its active bootstrap goal is `.devflow/goals/bootstrap-devflow-filesystem/`, and its project-level orientation starts at `.devflow/project/project.yaml`.

Proposed high-level structure:

```text
.devflow/
  project/
    project.yaml
    vision.md
    current-state.md
    architecture.md
    decisions.jsonl
    open-questions.jsonl
    glossary.md

  goals/
    <goal-id>/
      goal.yaml
      plan.md
      success.json
      status.md
      events.jsonl
      questions.jsonl
      decisions.jsonl
      context/
        active.md
        relevant-files.md
        constraints.md
        deferred-ideas.md
        rejected-ideas.md
      tasks/
        <task-id>.ref

  tasks/
    README.md
    <task-id>/
      task.yaml
      packet.md
      worker-report.md
      verification.json
      events.jsonl
      questions.jsonl
      decisions.jsonl
      logs/
        worker.log
        verify.log
      workspace/

  context/
    active/
      README.md
    reference/
      README.md
    archived/
      README.md
    deprecated/
      README.md
    rejected/
      README.md

  layers/
    product/
      vision.md
      user-problems.md
      success-metrics.md
    architecture/
      system-map.md
      boundaries.md
      state-model.md
      contracts.md
      decisions.jsonl
    implementation/
      current-slice.md
      file-map.md
      known-gaps.md
      active-constraints.md
    verification/
      verification-strategy.md
      commands.md
      known-failures.md
    operations/
      workflow.md
      agent-coordination.md
      recovery.md
      promotion.md

  workers/
    registry.yaml
    profiles/
      <profile>.yaml

  models/
    registry.yaml
    scoreboard.jsonl

  locks/
    README.md
    write.lock
    task-<task-id>.lock
    branch-main.lock

  reports/
    README.md
    daily/
    task-summaries/
    model-scorecards/
```

### Major Areas

`project/` contains project-wide truth and orientation. This is the smallest durable project brain. It should describe what Dev-Flow is, what state it is currently in, and which decisions are already settled.

`goals/` contains durable goal objects. A goal owns success criteria, goal-specific plans, goal-specific decisions, goal-local context, and links to tasks.

`tasks/` contains bounded execution units. A task owns its own packet, logs, worker report, verification result, events, questions, decisions, and isolated workspace.

`context/` contains classified reusable context. This prevents stale, deprecated, archived, or rejected ideas from being accidentally treated as current truth.

`layers/` contains the nested living knowledge structure. Each layer should contain only the context relevant to that level:

- Product layer: why the system exists.
- Architecture layer: how the system is shaped.
- Implementation layer: what is currently being built.
- Verification layer: how truth is checked.
- Operations layer: how humans and agents safely work.

`workers/` contains worker definitions and permission profiles.

`models/` contains model registry and scoreboard data.

`locks/` contains explicit write, task, and branch locks so multiple agents do not collide.

`reports/` contains derived summaries. Reports are useful, but never canonical authority.

Archive material is quarantined outside the active repository tree. If old material is needed again, restore only the useful part as an intentional active or reference document with current authority markings.

### Context Rules

- Every level should be locally understandable.
- Each folder should contain only relevant information for that layer.
- Active context must be separated from archived, deprecated, rejected, and experimental material.
- A newer file should explicitly supersede older guidance when applicable.
- Derived reports and summaries are not authoritative.
- Canonical runtime state lives in YAML, JSON, and JSONL files.
- Human-readable markdown explains intent, context, and rationale.
- Old plans must not be kept as in-repo junk. Preserve them outside the active tree, or restore only the useful part as active/reference context with clear current authority.
- The structure must support living development: new gaps, pivots, deferred ideas, rejected ideas, and updated decisions should have obvious homes.
- Do not flatten product memory into generic docs, workflows, or agent instructions; `.devflow/` is the durable control-room context model.

### Context Congruence

Context congruence means all levels of the filesystem should agree about the current direction of the project. When a goal, architecture decision, or implementation plan changes, the relevant project, goal, task, and layer files must be updated or explicitly marked stale.

Examples:

- If an architecture decision changes, update `layers/architecture/decisions.jsonl` and any affected goal context.
- If a brainstorm idea is rejected, move or mark it under rejected context.
- If an old plan is superseded, mark it with `superseded_by` pointing to the newer plan.
- If a task reveals a gap, record it in the task events and promote it to goal or project context only when validated.

### Context Promotion

Context promotion means information starts local to the place it was discovered, then moves upward only when it becomes broadly relevant.

Flow:

```text
task discovery -> goal context -> project context -> architecture/product layer
```

Example:

A worker finds that task packets need stale-context exclusion. First record it in the task events. If confirmed, add it to the goal context. If it affects all future Dev-Flow work, promote it to project architecture or contracts.

### Context Demotion

Context demotion means information that is obsolete, rejected, duplicated, or no longer relevant should be moved out of active context without being destroyed.

Flow:

```text
active -> reference -> archived/deprecated/rejected
```

This keeps the system clean without losing history.

### Filesystem Design Principle

The filesystem should reduce context load, not increase it. A worker should be able to open the smallest relevant folder and understand its job without absorbing the entire project history.

### Structure Acceptance Criteria

- The document defines the layered filesystem/context structure.
- The document explains active, reference, archived, deprecated, and rejected context.
- The document defines context congruence, context promotion, and context demotion.
- The document treats the filesystem as Dev-Flow's durable context layer, not just storage.

---

## 4. Goal Contract

A goal is a durable filesystem object, not a fleeting chat instruction.

- **`goal.yaml` Purpose**: Defines the high-level objective, global constraints, machine-checkable success criteria, and completion rules.
- **Required Fields**: `id`, `status`, `objective`, `constraints`, `success_criteria`, `iteration_policy`.
- **Success Criteria**: Must use stable, machine-readable IDs with explicit, programmatic verification checks (e.g., file existence, command execution).
- **Iteration Policy**: Dictates maximum attempts before escalation or pausing.
- **Completion Evidence**: A goal is complete only when all success criteria are verified to have passed, final verification succeeds, and a human explicitly signs off.

### Example `goal.yaml`
```yaml
id: local-model-workers
status: active
objective: Make local models usable as Dev-Flow workers.
constraints:
  - no auto-merge
  - no hidden state
  - no model-owned truth
  - no broad rewrites
  - one writing worker at a time
success_criteria:
  - id: model-registry-exists
    description: A model registry exists.
    verification:
      type: file_exists
      path: .devflow/models/registry.yaml
  - id: bounded-task-packets
    description: Dev-Flow can generate bounded task packets.
    verification:
      type: command
      command: PYTHONPATH=src pytest tests/test_task_packet.py -q
  - id: isolated-worker-attempt
    description: A worker can attempt a task in an isolated workspace.
    verification:
      type: command
      command: PYTHONPATH=src pytest tests/test_worker_workspace.py -q
iteration_policy:
  max_attempts_per_task: 3
  escalate_after_failures: 3
  require_verification: true
  require_human_completion_approval: true
```

---

## 5. Task Contract

A task is a durable unit of bounded work.

- **`task.yaml` Purpose**: Represents an isolated slice of a goal, mapping target files, strict barriers, and dedicated check commands.
- **Objective & Linking**: Must declare a clear `objective` and a `goal_id` mapping to its parent goal.
- **Scope Restriction**: Contains an explicit whitelist (`allowed_files`) and blacklist (`blocked_files`). Workers receive only whitelisted files; any mutation to a blocked file invalidates the attempt.
- **Constraints**: Extra limitations (e.g., "smallest useful patch", "tests required").
- **Verification**: Declares the exact shell check command to run.
- **Completion Rules**: Dictates requirements (e.g., verification pass, no unexpected file modifications, presence of worker report).

### Example `task.yaml`
```yaml
id: task-042-local-model-registry
goal_id: local-model-workers
status: ready
objective: Add a basic model registry skeleton.
scope:
  allowed_files:
    - src/devflow/models/
    - tests/test_model_registry.py
  blocked_files:
    - src/devflow/control_room/promotion.py
    - .github/
    - pyproject.toml
constraints:
  - smallest useful patch
  - no behavior outside model registry
  - no auto-routing
  - tests required
verification:
  command: PYTHONPATH=src pytest tests/test_model_registry.py -q
completion_rules:
  require_verification_passed: true
  require_allowed_files_only: true
  require_worker_report: true
```

---

## 6. State Machines

Durable state rules govern all transitions to ensure the control loop cannot drift into undefined or corrupt configurations.

### Goal States
`draft` -> `active` <-> `paused` | `blocked` | `escalated` -> `complete` | `abandoned`

```
  [ draft ]
      |
      v
  [ active ] <------> [ paused ]
    |  |  |
    |  |  +---------> [ blocked ] ----> [ escalated ]
    |  |                                     |
    |  +-------------------------------------+
    v
[ complete ] or [ abandoned ]
```

- **Valid Transitions**:
  - `draft` -> `active`
  - `active` <-> `paused`
  - `active` <-> `blocked`
  - `active` -> `escalated`
  - `blocked` -> `escalated`
  - `active` -> `complete` (Only when success criteria are fully met and human approves)
  - `active` -> `abandoned`
- **Invalid Transitions**:
  - `complete` -> `active`
  - `blocked` -> `complete` (without evidence)
  - `escalated` -> `complete` (without human approval)
  - `abandoned` -> `active` (without human approval)

### Task States
`created` -> `ready` -> `assigned` -> `attempting` -> `verification_pending` -> `verified_passed` | `verified_failed` -> `complete` | `blocked` | `abandoned`

```
[ created ] -> [ ready ] -----------> [ abandoned ]
                 | ^
                 v | (on failure)
            [ assigned ]
                 |
                 v
            [ attempting ]
                 |
                 v
        [ verification_pending ]
             /            \
            v              v
    [ verified_passed ]  [ verified_failed ]
            |              /         \
            v             v           v
       [ complete ]   [ ready ]   [ blocked ]
```

- **Valid Transitions**:
  - `created` -> `ready`
  - `ready` -> `assigned`
  - `assigned` -> `attempting`
  - `attempting` -> `verification_pending`
  - `verification_pending` -> `verified_passed`
  - `verification_pending` -> `verified_failed`
  - `verified_passed` -> `complete` (Upon promotion candidate evaluation)
  - `verified_failed` -> `ready` (For retry)
  - `verified_failed` -> `blocked` (For escalation)
  - `blocked` -> `ready` (Once unblocked by human or dependency)
  - `ready` -> `abandoned`

*Rule:* State changes must be logged programmatically with exact timestamps and initiating actors in the corresponding `events.jsonl` files.

---

## 7. One-Step Controller Contract

The core primitive of the MVP controller is a single, discrete action:

```bash
devflow goal step
```

### Rule: One goal step equals exactly one visible state transition.
A single invocation of the step command evaluates the filesystem state, executes a single logic transition, and writes the output. It **must not** hide an autonomous loop or invoke recursive workers.

A single step can perform exactly one of:
1. **Create one task**: Scaffolds a new `task.yaml` for an unmet goal criterion.
2. **Assign one task**: Pairs a `ready` task to an idle worker.
3. **Run one worker attempt**: Invokes a worker on a task packet in its workspace.
4. **Run one verification**: Executes the verification command on the workspace.
5. **Mark one task blocked**: Sets status to `blocked` and appends structured blocking evidence.
6. **Ask one human question**: Appends a structured query to `questions.jsonl` and pauses.
7. **Update success criteria**: Marks a success criterion satisfied based on verified evidence.
8. **Pause/escalate one goal**: Transitions goal state due to iteration limits or failures.

*Durable Trail:* Every step must record:
- What changed.
- Why it changed (eval logic).
- Which input triggered it.
- Which artifact proves it.
- What the next safe action is.

---

## 8. Task Packet Contract

A task packet is the strict, pruned context sent to a worker. It serves as the worker's short-term memory.

### The Budget Rule
The workspace filesystem may be huge; the task packet **must** be small.

- **Included**:
  - Task objective and linked goal criteria.
  - Allowed files (full contents or exact paths).
  - Explicit whitelisted dependency files.
  - Recent event history (last 5 events).
  - Latest verification failures/logs.
  - Strict stop rules and reporting formats.
- **Excluded**:
  - Unrelated codebase brainstorms or deprecated plans.
  - Large binary assets, build logs, or caches.
  - Secrets, tokens, or system-level environment credentials.
  - Full git histories (unless whitelisted).
- **Packet Policy Limits**:
  - Max Whitelisted Files: 8
  - Max total characters in packet context: 40,000 chars.

---

## 9. Worker Contract

A worker is a bounded executor, defined by:
`worker = model + machine + permission mode + workspace + task packet + stop rules`

Workers are actuators. They do not own truth, scope, verification, or promotion.

### Permission Modes
- `read_only`: Can inspect whitelisted files but write nothing. Useful for planners and auditors.
- `review_only`: Can inspect whitelisted files, task logs, and write a human-readable review.
- `test_only`: Can only execute test suites inside the task workspace.
- `workspace_write`: Can write and edit whitelisted files strictly inside the assigned workspace.
- `verify_only`: Can run verification commands and record outputs.

### Bounded Instruction Posture
Workers must be prompted as strictly constrained, narrow processors:
> "You are a bounded worker. Dev-Flow owns state, scope, verification, and promotion. You are sandboxed in your workspace. Perform only the assigned task, edit only whitelisted files, and stop immediately if blocked."

---

## 10. Locking Contract

To allow parallel operations without git collision or state corruptions, Dev-Flow enforces strict filesystem locks.

- **Write Lock (`write.lock`)**: A global write lock that represents ownership of a target branch. Only one active worker may hold this lock.
- **Task Lock (`task-<id>.lock`)**: A resource lock representing that a task workspace is currently executing.
- **Rules**:
  - No worker may bypass a lock by writing directly to main.
  - Read-only reviewers are permitted to inspect workspaces without write locks.
  - **Stale Lock Detection**: Locks include an expiry heartbeat. If a lock is stale, it must be explicitly resolved or overridden via CLI command (`devflow unlock <id>`).

---

## 11. Verification Contract

Verification belongs entirely to Dev-Flow. Workers may run checks locally, but only Dev-Flow-initiated verifications write canonical results to `verification.json`.

`verification.json` must capture:
- **`command`**: The exact shell command executed.
- **`exit_code`**: Subprocess return code.
- **`status`**: `passed` or `failed`.
- **`allowed_files_only`**: Boolean indicating if changes stayed within the whitelisted paths.
- **`unexpected_files`**: Whitelist violations (must fail verification if non-empty).
- **`log_path`**: Location of raw `verify.log`.
- **`timestamp`**: Accurate execution completion time.

*Rule:* Passing tests is necessary but not sufficient. A task with passing tests that edited a blocked file (e.g. `pyproject.toml`) will be marked `verified_failed` due to scope violations.

---

## 12. Blocked / Question Contract

When a task gets stuck, it must produce structured, machine-reusable evidence rather than vague conversational chat.

- **Blocking Causes**: Scope ambiguity, missing file dependencies, permission denials, repeat execution failures.
- **Structured Question (`questions.jsonl`)**:
  - `id`: Stable ID (e.g., `q-003`).
  - `task_id`: Linked task.
  - `question`: Clear description of the blocking decision.
  - `options`: List of explicit choices.
  - `recommended`: The worker's suggested option.
  - `reason`: Reasoning context.
  - `status`: `open` or `resolved`.

*Impact:* This keeps human intervention clean, rapid, and fully recorded inside the decision trail.

---

## 13. Recovery Contract

Durable loops must survive agent crashes, machine sleep, terminal terminations, and power loss.

- **Hartbeat Auditing**: At startup, Dev-Flow scans locks and statuses.
- **Attempt Stale**: If a task status is `attempting` but has no active heartbeat, Dev-Flow transitions it to `ready` or `blocked` and releases the lock.
- **Unverified Output**: If workspace edits exist but no `verification.json` is found, status is set to `verification_pending`.
- **Malformed Canonical State**: If `task.yaml` or `goal.yaml` is corrupted, the controller halts immediately and escalates to the human.
- **Scope Violation**: If a workspace shows modifications to `blocked_files` post-run, the workspace is discarded, and the task transitions to `verified_failed`.

---

## 14. Promotion Contract

Verified does not automatically mean promoted. No AI worker promotes to main.

### Promotion Pipeline
```
[ Worker Workspace Edit ]
         |
         v
[ Dev-Flow Task Verification ]
         |
         v
[ Scope & Cleanliness Validation ]
         |
         v
[ Task Marked Verified ]
         |
         v
[ Promotion Candidate Prepared (Durable Patch) ]
         |
         v
[ Human Code Review / Approval ]
         |
         v
[ Full Integration Branch Verification ]
         |
         v
[ Applied to Main ]
```

*Invariants:*
- AI workers never write directly to integration or main branches.
- Diffs are staged as clean, virtualized patch files before human approval.
- An explicit human CLI or dashboard action is required to promote.

---

## 15. MVP Rebuild Sequencing

To prevent speculative over-engineering, implementation must follow a strict, layered sequence.

```
+-------------------------------------------------------------+
| Phase 8: Scoreboard (Attempt/failure statistics & metrics)  |
+-------------------------------------------------------------+
| Phase 7: Local Worker Registry (Worker profiles & registry) |
+-------------------------------------------------------------+
| Phase 6: Worker Shell Adapter (Boring shell adapter kernel) |
+-------------------------------------------------------------+
| Phase 5: Locking (Global and task-level lock gates)         |
+-------------------------------------------------------------+
| Phase 4: Blocked & Questions (Structured Q&A logs)          |
+-------------------------------------------------------------+
| Phase 3: Task Verification (verify command & results JSON)  |
+-------------------------------------------------------------+
| Phase 2: One-Step Loop (devflow goal step primitive)        |
+-------------------------------------------------------------+
| Phase 1: Canonical State (goal.yaml, task.yaml schemas)     |
+-------------------------------------------------------------+
```

1. **Phase 1: Canonical State**
   - Implement `goal.yaml`, `task.yaml`, `verification.json`, `events.jsonl`, and `questions.jsonl` schemas.
   - Command: `devflow goal create`, `devflow goal status`, `devflow task status`, `devflow doctor`.
2. **Phase 2: One-Step Loop**
   - Implement `devflow goal step` command performing single state transitions.
3. **Phase 3: Task Verification**
   - Implement `devflow task verify <task_id> --shell <cmd>`.
   - Checks allowed paths and records `verification.json`.
4. **Phase 4: Blocked & Questions**
   - Implement structured `questions.jsonl` log and `devflow question answer` commands.
5. **Phase 5: Locking**
   - Implement file-based concurrency locking for workspaces and branches.
6. **Phase 6: Worker Shell Adapter**
   - Implement sandbox workspace creation, worker log capture, and report harvesting.
7. **Phase 7: Local Worker Registry**
   - Implement `workers/registry.yaml` and profiles.
8. **Phase 8: Scoreboard**
   - Track pass/fail metrics, cost, and token-saving statistics per model.

---

## 16. Two-Machine Strategic Coordination

Maximize hardware strengths safely:

### 1. Mac Studio M4 Max (64GB RAM)
*Role: Architect, Reasoning Planner, Hard Debugger, and Large Model Host.*
- Runs high-reasoning planners and reviewers.
- Performs multi-file reasoning, deep diagnostics, and model bakeoffs.
- Hosts larger local models (e.g., 32B+ models) or routes to supervisor handoffs.

### 2. Mac mini M1 (16GB RAM)
*Role: Bounded Task Worker, Document Auditor, and Test Runner.*
- Persistent execution node using bounded packets routed through the current model-router-managed fleet.
- Processes small, highly-bounded task packets.
- Runs verification tests, formats documentation, and tracks workspace states.
- *Advantage:* Persistent, cheap, local labor. Bounded packets ensure M1 memory constraints are never violated.
