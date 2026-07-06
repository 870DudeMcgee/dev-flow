# Dev-Flow Domain Context

Status: active vocabulary for architecture reviews.

This file records domain terms used by architecture and refactoring work. Product authority still lives in `PRODUCT_NORTH_STAR.md` and `docs/control-room-mvp.md`; this file exists so agents use stable names when discussing Modules, Interfaces, Seams, and Adapters.

## Terms

### Control room

The local-first Dev-Flow operating surface that lets the operator see tasks, workers/models, evidence, verification, review readiness, and next safe actions without digging through raw logs.

### Repo loop cockpit

The narrowed Dev-Flow operating surface for one selected repository. It guides Brainstorm, loop selection, worker/model output review, verification evidence, and promotion gates for active repo work.

The Repo loop cockpit does not own broad capture, daily context, project library, parking lots, or cross-project knowledge surfaces; those belong to the Obsidian Command Center.

### Obsidian Command Center

The broader local operating surface launched from Obsidian that owns durable data, projects, daily context, broad capture, parking lots, and cross-project knowledge. It can hand curated repo work into Dev-Flow, but it is not the repo execution cockpit.

### Curated handoff packet

A narrow Obsidian-to-Dev-Flow boundary object containing selected repo work, source links, intent, constraints, loop preference, acceptance criteria, and required docs.

### Repo picker

A minimal Dev-Flow selector that chooses the active repository for the Repo loop cockpit and shows only pre-loop repo health needed for safe operation.

### Brainstorm-first cockpit flow

The primary Dev-Flow repo workflow that starts with Brainstorm and reaches loop selection only after classification, spec, plan, and loop-packet shaping.

### Guided pipeline

The Dev-Flow cockpit flow that forces good repo-work practices by requiring each stage to produce the artifacts needed by the next stage before execution proceeds.

### Classification gate

A visible decision point after Brainstorm that labels the work type, explains the recommended route, and exposes eligible loop choices before spec and plan escalation.

### Hermes loop runtime

The external runtime provider that executes deterministic tool lanes, proven loops, fleet routing, codebase mapping, compression, and local-model escalation workflows for Dev-Flow cockpit packets.

### Deterministic tool lane

A Hermes runtime path that uses parsers, analyzers, extractors, verifiers, and failure classifiers for mechanical work before escalating to local models.

### Model escalation

A deliberate move from a Deterministic tool lane to a model-backed worker or supervisor when the work needs reasoning, seam judgment, product judgment, UI judgment, generation, or diagnosis beyond deterministic failure classes.

### Loop job preset

A curated Dev-Flow cockpit option that maps an operator job to a Hermes loop packet shape without creating a separate loop engine.

### Edit-capable loop preset

A Loop job preset that may write files through the shared Hermes edit-loop mechanics, with its safety determined by default write scope, risk gate, and expected artifact.

Default write budgets:
- **Spec/Planning Loop** writes planning docs, packet files, dependency/tool notes, test-plan notes, and small probe scripts only with approval.
- **Builder-Judge Loop** writes implementation files and directly related tests named in the packet.
- **Verify-Fix Loop** writes files implicated by failing verification plus directly related tests.
- **Refactor/Recovery Loop** writes a plan artifact first; code edits require a bounded file list or second approval.

### Spec/Planning Loop

The edit-capable Loop job preset that produces or updates planning artifacts and the exact implementation packet, including dependencies, stack, APIs, machine quirks, installed tools, required installs, file names, source anchors, verification commands, risks, and acceptance criteria.

### Builder-Judge Loop

The normal code-writing Edit-capable loop preset that consumes a planning packet, edits bounded files, judges output, and iterates until approved or blocked.

### Builder-Judge readiness packet

The required artifact set before Builder-Judge can run: objective, selected repo, exact file targets or discovery scope, dependencies/tooling notes, machine quirks, API/data contracts, acceptance criteria, verification commands, allowed write scope, stop conditions, and supervisor intent summary.

### Supervisor intent summary

A short cloud/frontier-authored bridge from messy operator intent to product outcome, non-negotiables, likely worker misunderstandings, and the felt definition of done.

### Repo execution artifact

A Dev-Flow-owned file under the selected repository's `.devflow/` directory that records readiness packets, loop packets, run evidence, verification results, review gates, or promotion decisions for that repo.

### Pipeline run

The primary Dev-Flow guided-cockpit record for one Brainstorm-to-loop-to-review journey in a selected repository.

A Pipeline run contains intent, source, brainstorm, classification, readiness packet, loop packet, validation, run log, artifacts, and review records under `.devflow/pipeline-runs/<run_id>/`.

V1 Pipeline runs link to existing Brainstorm sessions and compatibility Task records instead of replacing or migrating them.

### Implementation ledger

A detailed Dev-Flow planning artifact that tracks redesign slices, status, target files, dependencies, verification, risks, and the next action for each implementation step.

### Verify-Fix Loop

The Edit-capable loop preset that starts from verification commands or failures, diagnoses issues, applies narrow fixes through the builder-judge pattern, and returns to the Verification gate.

### Refactor/Recovery Loop

The higher-risk Edit-capable loop preset for architecture cleanup or failed runs that need codebase mapping, recovery planning, or refactor strategy before changing broader code.

### Active loop fleet

The simplified Hermes loop routing set used by Dev-Flow. The active local fleet
is only Ornith 35B on `8084` for scout/build work and Qwen 27B MTP on `8083`
for judging. Ornith runs with `-np 3`, so up to three independent scout/builder
jobs can share the one Ornith process. Ornith and Qwen cannot run
simultaneously; the model-router swaps between them.

Retired models such as Ornith 9B, Qwopus 35B, and Qwen3-Coder-Next may still
exist in old docs or local config, but they are not active Dev-Flow scout,
builder, judge, UI, fallback, or emergency lanes. Cloud/frontier models remain
intent bridges and supervisors.

### Fleet cleanup migration

A separate Hermes inventory and configuration cleanup task for removing obsolete local-model surfaces after Dev-Flow loop routing has stopped using them.

### Current-loop compatibility

The constraint that Dev-Flow's first Hermes integration must wrap the working loop setup with minimal runtime changes, while treating richer fleet routing as a later refinement.

### Hermes loop packet preview

An approval-and-edit gate that shows the exact Hermes loop packet before execution and lets the operator freely edit the packet before validation and launch.

### Packet validation gate

A post-edit safety check that blocks unsafe Hermes loop packets while leaving quality guidance as advisory warnings the operator can override.

### Loop run monitor

The Dev-Flow cockpit view that shows Hermes loop output live while also extracting compact checkpoints for phase, meaningful event, touched files, blockers, next action, and evidence path.

### Loop steering controls

The explicit Dev-Flow cockpit controls that let the operator pause, resume, stop, inject direction, request a checkpoint, or mark a Hermes loop run as needing review.

### Loop review gate

The Dev-Flow decision point after a Hermes loop run where returned artifacts, changed files, transcripts, handoffs, claimed completion, and verification commands are reviewed before promotion.

### Verification gate

The Dev-Flow-owned readiness check that runs or records verification against the selected repository state before promotion can be considered.

### Operating layer

The active browser product served by `devflow operating-layer serve`. It is a read-oriented projection over filesystem-backed Dev-Flow state plus a narrow approval-gated browser action path.

### Task

A Dev-Flow unit of work with durable state under `.devflow/tasks/<task_id>/`. A task owns its title, status, workspace, worker/model identity, logs, evidence, verification, close state, and promotion readiness.

### Worker lane

The operator-facing view of work owned by a worker or model for a task. A worker lane should show task title, status, worker/model, last update, evidence, and next action.

### Local model server

A resident local model process or endpoint that may serve model responses but has no task authority by itself.

### Worker profile

A named model, capability, and permission identity that can be selected by an execution surface but is not itself proof of readiness or completion.

### Execution surface

An approved Dev-Flow, Hermes, or Codex path that can consume a bounded packet and produce evidence under explicit authority limits.

### Local worker

An approved local model route acting through an execution surface to produce bounded task evidence.

### Fleet telemetry

Read-only evidence about whether local model lanes are configured, listening, loaded, smoke-proven, or mismatched.

### Review queue

The operator-facing list of tasks that need verification, review, human decision, or promotion action.

### Evidence stream

The operator-facing timeline or list of concrete task artifacts: events, logs, worker output, verification records, promotion previews, and other review evidence.

### Next safe action

The most useful action Dev-Flow can recommend without hiding safety requirements. It must name the task or project, expose the exact command when applicable, and make human approval requirements visible.

### Task workbench

The operator-facing projection that turns task state into the first usable work surface: selected task, Worker lanes, Review queue, Evidence stream, task controls, gate progress, worker/model identity, and next safe actions.

The Task workbench is not canonical state. It is a derived read model for usability and should remain backed by existing task artifacts, worker evidence, verification artifacts, and promotion readiness evidence.

### Context Map

A proposed standalone read-only codebase orientation tool that answers "where should I look, and why?" for a codebase task by combining current source indexes, Graphify evidence, `CODE_MAP.md`, active docs, and selected Obsidian memory notes.

Context Map may later expose an MCP server for Codex, Hermes, Dev-Flow, or other clients. It is not execution authority. It must not edit source, route workers, verify readiness, promote work, or silently write durable vault notes.

## Relationships

- A **Local model server** can support one or more **Worker profiles**.
- A **Worker profile** becomes a **Local worker** only through an **Execution surface**.
- A **Local worker** produces evidence for a **Task**; Dev-Flow verification decides readiness, closure, and promotion.
- **Fleet telemetry** describes local model availability; it is not task evidence or verification proof by itself.
- A **Context Map** can orient a worker before source inspection, but live source, tests, docs, and Dev-Flow verification still decide whether a change is correct.
- The **Obsidian Command Center** produces **Curated handoff packets** for the **Repo loop cockpit**.
- The **Repo loop cockpit** reports task, worker, evidence, verification, and promotion status back to the **Obsidian Command Center** without duplicating its broad project surfaces.
- A **Repo picker** opens a **Repo loop cockpit** for one repository; it is not a multi-project dashboard.
- **Repo execution artifacts** live under the selected repo's `.devflow/`; Obsidian links to and summarizes them rather than owning execution truth.
- A **Pipeline run** is the primary guided-cockpit record; traditional **Tasks** are compatibility records only where existing verification or promotion machinery requires them.
- The redesign plan is tracked through an **Implementation ledger** so future sessions can continue slice-by-slice without rediscovering scope.
- The **Repo loop cockpit** follows a **Brainstorm-first cockpit flow** so loop choice is based on shaped work rather than premature tool selection.
- The **Brainstorm-first cockpit flow** is a **Guided pipeline**; operators can edit packets freely, but cannot skip required artifact quality gates.
- A **Brainstorm-first cockpit flow** passes through a **Classification gate** before the cockpit presents loop choices.
- The **Repo loop cockpit** presents a **Hermes loop packet preview**, runs a **Packet validation gate**, sends a shaped packet to the **Hermes loop runtime**, and follows execution through a **Loop run monitor**.
- **Loop steering controls** send explicit operator direction into a running **Hermes loop runtime** without silently rewriting the packet or changing execution policy.
- A finished **Hermes loop runtime** run enters the **Loop review gate**; Hermes output is execution evidence, not promotion proof.
- The **Loop review gate** feeds a Dev-Flow-owned **Verification gate** before any promotion decision.
- A **Loop job preset** is one of four V1 **Edit-capable loop presets**: **Spec/Planning Loop**, **Builder-Judge Loop**, **Verify-Fix Loop**, or **Refactor/Recovery Loop**.
- **Builder-Judge Loop** requires a **Builder-Judge readiness packet** with a **Supervisor intent summary**, whether it was produced by Obsidian, Brainstorm, or Spec/Planning.
- The **Hermes loop runtime** should prefer a **Deterministic tool lane** for mechanical transformations and use local models when reasoning, seam selection, UI judgment, or generation actually adds value.
- **Model escalation** happens only after the **Deterministic tool lane** is insufficient or the work shape inherently needs model judgment.
- The **Active loop fleet** removes Ornith 9B, Qwopus 35B, and Qwen3-Coder-Next from Dev-Flow loop routing; they may remain installed as assets, but they are not part of the cockpit path.
- A **Fleet cleanup migration** may later remove obsolete Hermes config or UI references, but it is separate from defining the Dev-Flow cockpit path.
- The **Active loop fleet** treats cloud/frontier models as intent bridges and supervisors, not routine workers.
- **Current-loop compatibility** takes priority over immediately implementing the full desired fleet-routing matrix.

### Repository cleanup

A source-tree hygiene activity that classifies repository material before changing, archiving, untracking, or deleting it.

Repository cleanup candidates are classified as active product, compatibility bridge, generated/local runtime state, historical reference, future roadmap, stale context candidate, or stale artifact.

### Stale context candidate

A document or reference whose current accuracy is untrusted until reconciled against active product intent, code, tests, live Dev-Flow behavior, and fresh architecture evidence.

## Flagged ambiguities

- "cleanup" was used to mean both task-owned runtime cleanup and repository cleanup; resolved: the current cleanup grilling session means **Repository cleanup**.
- "local worker" was used to mean a model server, provider, profile, or runtime path; resolved: a **Local worker** is only an approved local model route acting through an **Execution surface**.
- "Obsidian integration" could mean browsing the whole vault from Dev-Flow or accepting a narrow work packet; resolved: Dev-Flow accepts **Curated handoff packets** and avoids becoming a second Obsidian browser.
- "execution artifact ownership" could drift into Obsidian; resolved: **Repo execution artifacts** live in `.devflow/` beside the repo state they govern.
- "repo picker" could mean a multi-project dashboard; resolved: it is a minimal doorway into one selected **Repo loop cockpit**.
- "every loop run is a task" would recreate task-management noise; resolved: use a **Pipeline run** as the primary cockpit record and create **Tasks** only for compatibility.
- "pipeline run" could imply migrating existing Brainstorm and Task state immediately; resolved: V1 links existing artifacts instead of replacing them.
- "detailed plan" could become a static essay; resolved: use an **Implementation ledger** with slice status, verification, and next actions.
- "choose loop first" could front-load tooling before the work is clear; resolved: Dev-Flow uses a **Brainstorm-first cockpit flow** and chooses a loop after the work has been classified and shaped.
- "optional planning" could let weak packets reach execution; resolved: the **Guided pipeline** requires the artifacts needed for safe execution, whether produced by Spec/Planning or supplied by a high-quality handoff.
- "classification" could be hidden model routing; resolved: it is a visible **Classification gate** with rationale and loop options.
- "integrate Hermes loops" could mean rebuilding Hermes behavior in Dev-Flow; resolved: Dev-Flow wraps the **Hermes loop runtime** instead of transplanting loop internals.
- "local model workflow" could become ceremony around mechanical work; resolved: use a **Deterministic tool lane** before model escalation when a parser/verifier can do the job exactly.
- "packet preview" could mean passive confirmation only or a field-by-field wizard; resolved: a **Hermes loop packet preview** is free-form editable before validation and execution.
- "packet validation" could mean more babysitting; resolved: the **Packet validation gate** blocks only safety violations and keeps quality concerns advisory.
- "live output" could mean either raw stream only or summary only; resolved: the **Loop run monitor** shows the stream and compact checkpoints together.
- "steering" could imply hidden mid-run mutation; resolved: **Loop steering controls** are explicit operator messages and lifecycle commands only.
- "loop finished" could mean ready to promote; resolved: completion enters the **Loop review gate** before verification and promotion.
- "verification" could mean trusting Hermes prechecks; resolved: promotion depends on a Dev-Flow-owned **Verification gate**.
- "loop catalog" could become a broad toolbox; resolved: V1 exposes four job-oriented **Loop job presets**.
- "Ornith 9B", "Qwopus", or "Qwen3-Coder-Next" could remain fallback lanes by inertia; resolved: the **Active loop fleet** excludes them from Dev-Flow/Hermes loop routing.
- "scrapping retired models" could mean immediate asset/config deletion; resolved: cockpit routing excludes them now, while physical/config cleanup belongs to a separate **Fleet cleanup migration**.
- "best model" could mean either smartest, fastest, or most reliable; resolved: the **Active loop fleet** separates Ornith scout/build throughput, Qwen judge precision, and frontier intent-bridge roles.
- "routing matrix" could imply rewriting the current loop setup; resolved: preserve **Current-loop compatibility** in V1 and refine routing after the cockpit works.
- "edit loop" could imply one generic write path with no shape; resolved: all four V1 loops are **Edit-capable loop presets** with different default write budgets, risk gates, and expected artifacts.
