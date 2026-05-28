# Dev-Flow North Star

## Product Identity

Dev-Flow is a local-first control room for parallel AI coding agents.

It exists to let a human developer coordinate many AI-assisted coding efforts across multiple projects without losing visibility, safety, context, or control.

Dev-Flow is not the coding intelligence itself. It is the operational layer around coding intelligence.

Agents, models, and tools are replaceable.

Dev-Flow owns the jobsite.

---

## One-Sentence Mission

Dev-Flow lets me run multiple AI coding workers in parallel, see exactly what they are doing, prevent them from stepping on each other, recover from failures, and approve only verified, reviewable work.

---

## The Problem Dev-Flow Solves

AI coding tools are powerful but chaotic when used in parallel.

They tend to:

- lose context
- overwrite each other's work
- hide failures in long logs
- hang silently
- require constant babysitting
- burn expensive frontier-model tokens on routine coordination
- make it hard to know what changed, what failed, and what needs human input

Dev-Flow solves this by making AI coding work:

- visible
- isolated
- stateful
- recoverable
- reviewable
- model-agnostic
- safe to run in parallel

---

## The Human Experience We Are Building Toward

The ideal user experience:

1. I describe what I want built.
2. Dev-Flow breaks or accepts the work as clear tasks.
3. Each task gets an isolated workspace.
4. A worker is assigned to each task.
5. Workers run in parallel when safe.
6. I can open the dashboard from my computer or phone.
7. I can instantly see:
   - what is running
   - what is blocked
   - what failed
   - what changed
   - what needs my input
   - what is ready to review
8. Workers ask me questions only when they genuinely need direction.
9. No worker can silently corrupt the main repo.
10. No work is considered complete until it is verified and reviewable.
11. Expensive frontier models are used only for hard reasoning, architecture, debugging, review, or escalation.
12. Routine implementation, testing, logging, and status tracking happen locally or cheaply.

The final feeling should be:

> "I have a small AI dev team working in parallel, but I can actually see, control, and trust the process."

---

## Core Philosophy

### 1. Agents are replaceable. State is sacred.

Dev-Flow must not depend on one model, one coding agent, one IDE, or one vendor.

Aider, Hermes, Codex, Claude Code, OpenCode, Gemini CLI, local models, shell scripts, and future tools should all be usable as workers.

Dev-Flow owns:

- task state
- project state
- workspace state
- worker status
- logs
- questions
- results
- verification state
- review readiness

Workers are replaceable execution engines.

---

### 2. Visibility is mandatory.

Dev-Flow is a control room.

If work is happening, the user must be able to see it.

Every running task must expose:

- status
- current step
- worker name
- workspace
- last heartbeat
- latest log line
- files changed
- test/verification result
- whether human input is needed

If the user has to dig through random logs to know what is happening, Dev-Flow is failing.

---

### 3. Isolation before autonomy.

Parallel work is only useful if workers cannot damage each other's work.

Every task should have a clear ownership boundary.

Preferred model:

```text
one task
-> one isolated workspace
-> one worker owner
-> one result bundle
-> one review/merge path
```

Workers should not share the main checkout.

Workers should not merge directly to main.

Workers should not touch files outside their allowed scope.

---

### 4. Context should be durable artifacts, not vague memory.

Dev-Flow should not rely primarily on hidden chat history or magical memory.

Important context should live in files that humans and agents can inspect:

- PROJECT_BRIEF.md
- ARCHITECTURE.md
- DECISIONS.md
- CURRENT_STATE.md
- task.md
- context.md
- questions.md
- result.md
- report.md
- diff.patch
- worker.log
- verify.log

A worker should be able to resume or hand off work from artifacts, not from invisible memory.

---

### 5. Autonomy is earned.

Dev-Flow should not assume agents are reliable.

Agents earn more autonomy by proving they can:

- work inside assigned boundaries
- update status honestly
- produce logs
- ask clear questions
- generate reviewable results
- pass verification
- avoid protected files
- recover from failure

Until then, Dev-Flow should favor visibility, review, and manual approval.

---

### 6. Failure should be clear, safe, and recoverable.

A failed task is acceptable.

A mysterious failure is not.

Every task should end in one of these understandable states:

- complete
- ready_for_review
- needs_human_input
- blocked_by_dependency
- worker_failed
- verification_failed
- timed_out
- cancelled
- stale

Failures should produce reports that explain:

- what happened
- what changed
- what command failed
- where the logs are
- what the likely next action is

---

### 7. Frontier models are architects and rescuers, not full-time employees.

Dev-Flow should minimize expensive model usage.

Local or cheap workers should handle:

- simple edits
- tests
- docs
- repetitive fixes
- small refactors
- status/report generation

Frontier models should be used for:

- architecture
- hard debugging
- unclear product decisions
- security review
- final review
- escalation when local workers are stuck

The product should continue to be useful even when Codex, Copilot, or paid credits are unavailable.

---

## Long-Term End State

A mature Dev-Flow system should support the following.

### 1. Multi-project control room

The user can manage multiple projects from one dashboard.

Example:

```text
Project A: 2 tasks running, 1 blocked, 1 ready for review
Project B: 1 task running, tests failing
Project C: waiting for user decision
```

---

### 2. Parallel worker execution

Dev-Flow can run multiple workers safely at the same time.

It enforces:

- max parallel workers
- per-task workspace isolation
- timeouts
- heartbeat monitoring
- dependency blocking
- protected path rules
- review before merge

---

### 3. Worker adapter system

Dev-Flow supports multiple worker types through adapters:

- shell
- Aider
- Hermes
- OpenCode
- Codex
- Claude Code
- Gemini CLI
- custom scripts
- local model agents

All workers obey the same contract:

```text
input: task + context + workspace + rules
output: status + logs + questions + result + diff/changes
```

---

### 4. Simple but useful dashboard

The dashboard should show:

- projects
- tasks
- statuses
- running workers
- stale workers
- blocked tasks
- open questions
- latest logs
- changed files
- verification results
- review-ready work

The dashboard should work locally and over a private network/Tailscale.

It should be useful before it is beautiful.

---

### 5. Question/answer loop

Workers should not guess when a human decision is needed.

They should write questions in a structured way.

Dev-Flow should surface those questions clearly.

The user should be able to answer from CLI or dashboard.

The answer should become part of the task context and decision history.

---

### 6. Verification and review gate

No work is done until it is verified or explicitly marked as unverified.

Dev-Flow should support:

- configured test commands
- lint/typecheck commands
- protected path checks
- allowed path checks
- diff summaries
- generated reports
- manual review
- safe merge

---

### 7. Durable audit trail

Every task should leave behind enough information to understand what happened later:

- task definition
- assigned worker
- workspace
- logs
- questions
- answers
- changed files
- verification output
- result summary
- final status

This is how Dev-Flow becomes trustworthy.

---

## Near-Term MVP

The first production-worthy MVP is not a full AI swarm.

The first MVP is a non-AI control room that proves the infrastructure works.

The frozen shell-worker MVP contract is documented in [docs/mvp-contract.md](docs/mvp-contract.md). It is smaller than the long-term control-room vision and intentionally excludes database state, worktree orchestration, dashboards, AI worker adapters, and copy-back/merge behavior.

Required commands:

```bash
devflow --help
devflow task --help
devflow task create "example task"
devflow task run <task_id> --shell "echo hello > result.txt"
devflow task verify <task_id> --shell "test -f result.txt"
devflow task show <task_id>
devflow task list
```

Required capabilities:

- create per-task filesystem artifacts
- run shell workers
- run verification commands
- capture worker and verification logs
- keep worker writes in the task workspace
- show status in CLI
- refuse tampered workspace paths
- skip symlinks during scratchpad copy
- avoid SQLite databases and `.devflow/worktrees/`

Required runtime shape:

```text
.devflow/
  tasks/<task_id>/
    task.yaml
    events.jsonl
    verification.json
    logs/
      worker.log
      verify.log
  workspaces/<task_id>/
```

The MVP passes when Dev-Flow can create one shell task, run `echo hello > result.txt`, verify `test -f result.txt`, list it, and show it while keeping `result.txt` out of the main checkout.

---

## What Not To Build Yet

Do not build these until the control room works:

- complex autonomous planning
- memory/vector database
- Aider integration
- Hermes integration
- OpenCode integration
- Codex integration
- multi-agent reasoning
- PR automation
- cloud deployment
- fancy dashboard design
- plugin marketplace
- complex DAG planner
- self-improving agent behavior

These are future layers.

The control room comes first.

---

## Roadmap

### Phase 1: Frozen Shell-Worker Foundation

Goal: prove task state, shell worker execution, verification, logs, CLI visibility, and workspace-only writes.

Deliverables:

- `devflow --help`
- `devflow task --help`
- `devflow task create "example task"`
- `devflow task run <task-id> --shell "echo hello > result.txt"`
- `devflow task verify <task-id> --shell "test -f result.txt"`
- `devflow task list`
- `devflow task show <task-id>`

Success check:

```text
Can I create, run, verify, list, and show one shell task while keeping worker writes out of the main checkout?
```

---

### Phase 2: Workspace Safety

Goal: prevent workers from stepping on each other.

Deliverables:

- copied scratchpad workspace per task
- tampered workspace path refusal
- symlink skipping during scratchpad copy
- explicit future design for copy-back or promotion

Success check:

```text
Can a shell worker produce results without touching the main checkout?
```

---

### Phase 3: Verification Gate

Goal: make work reviewable and safe.

Deliverables:

- verify commands
- verification logs
- latest verification JSON
- verified and verification_failed statuses
- future protected path, diff, report, and ready_for_review design

Success check:

```text
Can a task produce a diff, run tests, and become ready for human review?
```

---

### Phase 4: Question Loop

Goal: stop workers from guessing.

Deliverables:

- questions.md
- structured open questions
- CLI answer command
- dashboard questions panel
- answers added to task context

Success check:

```text
Can a worker stop, ask for direction, receive an answer, and preserve that decision?
```

---

### Phase 5: Simple Scheduler

Goal: run safe parallel work.

Deliverables:

- ready queue
- max parallel workers
- timeout handling
- stale heartbeat detection
- dependency blocking
- manual retry

Success check:

```text
Can Dev-Flow run multiple tasks in parallel without losing state or creating chaos?
```

---

### Phase 6: First AI Worker Adapter

Goal: plug in replaceable coding intelligence.

First adapter should be one of:

- Aider
- OpenCode
- Hermes
- Codex CLI / extension command wrapper

Deliverables:

- WorkerAdapter interface
- AI worker command wrapper
- context bundle passed to worker
- logs captured
- questions captured
- result artifacts captured

Success check:

```text
Can an AI worker complete a small task inside an isolated workspace and leave a reviewable result?
```

---

### Phase 7: Foreman/Supervisor Integration

Goal: allow a smarter agent like Hermes or a frontier model to supervise work without owning Dev-Flow state.

Deliverables:

- read-only status API
- command/API for creating tasks
- command/API for answering questions
- supervisor instructions
- escalation policy

Success check:

```text
Can a supervisor agent inspect Dev-Flow state, assign work, and summarize progress without bypassing Dev-Flow safety?
```

---

### Phase 8: Multi-Project Operation

Goal: support the original dream.

Deliverables:

- project registry
- project-level dashboard
- per-project config
- per-project context docs
- cross-project task status
- mobile-friendly dashboard

Success check:

```text
Can I see and manage multiple projects from one control room?
```

---

## Periodic Self-Check For AI Assistants

Any AI working on Dev-Flow should periodically answer these questions:

1. Are we building the control room, or are we accidentally building another coding agent?
2. Does this change make parallel work more visible, isolated, or recoverable?
3. Does this change reduce or increase process ceremony?
4. Is state becoming clearer or more scattered?
5. Can the user tell what is happening without reading huge logs?
6. Does this work without paid frontier-model credits?
7. Are workers still replaceable?
8. Are we protecting the main repo?
9. Are failures understandable?
10. Is this useful in the MVP, or is it speculative future architecture?

If the answer shows drift, stop and simplify.

---

## Definition of Success

Dev-Flow succeeds when the user can say:

> "I have multiple AI coding workers moving projects forward in parallel, and I can see what they are doing, stop them, answer questions, review their work, and trust that they will not silently wreck my repos."

That is the destination.

Everything we build should move toward that.
