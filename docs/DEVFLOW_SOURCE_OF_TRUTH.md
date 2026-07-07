# DevFlow Source of Truth

Status: Active canonical direction
Date: 2026-07-07

This document is the active source of truth for DevFlow.

Older architecture, roadmap, cockpit, orchestration, local-worker, model-routing, and software-factory documents are non-authoritative unless explicitly listed here as canonical references. Historical documents may be useful for recovery, but they must not be loaded as active context by default.

## One-Sentence Purpose

DevFlow is the local operating layer that turns a user's rough idea into a verified product implementation through brainstorm, specification, planning, planning review, bounded worker delegation, builder/judge execution, and evidence-backed verification.

## Working Principle

DevFlow's working principle is simple:

```text
Idea -> Brainstorm -> Spec -> Plan -> Judge -> Build -> Judge -> Verify -> Next human decision
```

The parts underneath may be complex, but every part exists only to advance this loop safely.

DevFlow does not exist to display all knowledge, manage every project fact, or become a general AI operating system. Obsidian owns the broad data and knowledge layer. DevFlow owns the active product-building loop.

## What DevFlow Is

DevFlow is:

- a local-first operating layer for creating products, programs, SaaS apps, websites, and software systems;
- a disciplined loop that forces vague ideas to become defined before implementation;
- a repo-aware spec and planning system that discovers the minimum real constraints needed to build safely;
- an orchestrator that routes bounded work to appropriate workers;
- a builder/judge execution loop that turns approved plans into verified changes;
- an evidence surface that shows what happened, why it happened, what verified it, and what is safe to do next.

## What DevFlow Is Not

DevFlow is not:

- a replacement for the human operator;
- a replacement for Obsidian;
- a replacement for Hermes;
- a replacement for Git or the filesystem;
- a broad knowledge dashboard;
- a universal autonomous software factory;
- a model zoo manager as its primary identity;
- a place where every historical architecture idea remains active context;
- a dashboard that invents state not backed by files, git, commands, tests, reports, or evidence.

## Ownership Boundaries

| Layer | Owns |
| --- | --- |
| User | Vision, taste, priority, acceptance, final decisions. |
| Obsidian | Broad data layer, personal/project knowledge, durable notes, long-term context. |
| DevFlow | Active product-building loop, task state, evidence, verification, routing, next safe action. |
| Git/filesystem | Actual source truth for code, docs, artifacts, diffs, and committed history. |
| Hermes | Runtime/tool/messaging harness used by agents and workflows, not DevFlow's identity. |
| Local models | Bounded labor: scout, spec, plan, build, judge, summarize. |
| Orchestrator | Stage control, context requests, routing, delegation, blocking, escalation, next action. |
| Builders | Small bounded implementation tasks. |
| Judges | Plan/build verification, scope enforcement, evidence review, pass/revise/block decisions. |

## The Product-Building Loop

### 1. Brainstorm and Definition Gate

A rough idea starts as a brainstorm. DevFlow must not jump directly from a vague idea to implementation.

The brainstorm stage forces definition:

- What is being built?
- Who is it for?
- What problem does it solve?
- What does success look like?
- What is in scope?
- What is out of scope?
- What existing repo, product, data, or environment does it touch?
- What must be decided by the human before implementation can start?

Output: an Idea Brief.

### 2. Spec Loop

The spec loop turns clarified intent into implementation-aware requirements.

It looks at the target repo and relevant environment only as much as needed to build safely:

- codebase structure;
- existing architecture and interfaces;
- dependencies and packages;
- runtime and machine requirements;
- filesystem paths and generated artifacts;
- reports and evidence sources;
- tests and verification commands;
- known constraints from Obsidian or other approved context sources.

The spec loop must not hoard context. It gathers the minimum facts required to advance the current product-building stage safely.

Output: an implementation-aware Spec.

### 3. Planning Loop

The planning loop converts the spec into executable work.

It identifies:

- implementation slices;
- task dependencies;
- required setup;
- required files and interfaces;
- worker assignments;
- what can run in parallel;
- what must be sequential;
- verification commands;
- evidence requirements;
- human approval points;
- rollback or recovery concerns.

Output: an Execution Plan made of bounded tasks.

### 4. Planning Judge

Before execution, a judge reviews the plan.

The planning judge asks:

- Is the plan grounded in the repo and environment?
- Are tasks small and bounded?
- Are dependencies and prerequisites known?
- Are verification commands real?
- Are risk and approval boundaries clear?
- Is the plan overbuilt?
- Is there a simpler path?

The judge returns one of:

- `APPROVE`
- `REVISE`
- `BLOCK`
- `ESCALATE_TO_USER`

Output: an approved or revised executable plan.

### 5. Orchestrator

The orchestrator is a traffic controller, not the builder.

It decides:

- what stage the loop is in;
- what information is missing;
- which worker should do which bounded task;
- when to search, inspect, or ask the user;
- when to call a judge;
- when evidence is insufficient;
- when a task is blocked;
- when the loop can advance;
- what the next safe action is.

The orchestrator's normal output is:

```text
next bounded assignment + required context + acceptance evidence
```

If it cannot produce that, the loop moves backward to brainstorm, spec, or planning instead of pushing bad work into build.

### 6. Builder/Judge Execution

Builders execute small implementation tasks. Judges verify that the tasks were done correctly.

Builders receive bounded assignments such as:

- add this endpoint;
- update this test;
- wire this UI control;
- generate this migration;
- fix this failing verification;
- summarize this evidence packet.

Build judges ask:

- Did the worker do the assigned task?
- Did it stay in scope?
- Did files or artifacts actually change as claimed?
- Did verification pass with real command output?
- Is the evidence sufficient?
- Is it safe to continue?

Output: a verified or rejected implementation slice.

### 7. Verification and Next Human Decision

DevFlow must always be able to answer:

- What are we trying to build?
- What stage is the loop in?
- What work is active?
- What changed?
- Who or what changed it?
- What evidence proves it?
- What failed or remains unknown?
- What is safe for the human to do next?

Output: evidence-backed next action.

## Canonical Stage Artifacts

DevFlow should prefer a small set of stage artifacts over sprawling architecture docs.

| Artifact | Produced By | Purpose |
| --- | --- | --- |
| Idea Brief | Brainstorm | Captures clarified product intent, scope, non-goals, open questions. |
| Spec | Spec loop | Captures implementation-aware requirements and constraints. |
| Execution Plan | Planning loop | Captures slices, dependencies, worker assignments, verification, risks. |
| Judge Report | Planning/build judges | Captures approve/revise/block decisions and evidence-backed findings. |
| Verification Ledger | Execution/verification | Captures commands, outputs, changed files, pass/fail, final state, next action. |

These artifacts should be compact, current, and attached to the active loop. They are not a license to recreate the old architecture swamp.

## Context Policy

DevFlow gathers only the context required to advance the current product-building stage safely.

Approved context sources include:

- current repo files;
- git state;
- generated reports and evidence artifacts;
- verification command output;
- explicit user input;
- bounded context packets from Obsidian or other approved data-layer tools.

DevFlow should not load old architecture documents, archived plans, generated reports, or prior speculative designs as active context unless explicitly directed by the user.

## Documentation Policy

Active DevFlow documentation should be sparse and operational.

A document remains active only if it directly supports one of:

1. brainstorm and idea definition;
2. spec loop;
3. planning loop;
4. planning judge;
5. orchestrator routing;
6. builder/judge execution;
7. evidence and verification;
8. Obsidian-vs-DevFlow boundary;
9. local worker/runtime boundary;
10. user-facing operation of the current loop.

Historical docs should be quarantined or deleted. Quarantined docs are non-authoritative recovery material and must not be loaded by default.

## Canonical References

The following files may remain active when they are kept aligned with this source of truth:

- `AGENTS.md` — repo-specific agent operating rules.
- `README.md` — project entrypoint and user-facing summary.
- `docs/DEVFLOW_SOURCE_OF_TRUTH.md` — this document.
- `docs/local-worker-policy.md` — compact local worker boundary, if kept short and aligned.
- `docs/verification-ledger.md` — evidence history, if kept factual and non-prescriptive.

Any other document must earn active status by directly supporting the current loop. Otherwise it belongs in quarantine, archive, or deletion.

## Non-Negotiable Principles

- Force definition before implementation.
- Build from real repo/environment facts, not vibes.
- Gather enough context to proceed safely, not all possible context.
- Keep workers bounded.
- Do not let builders verify themselves.
- Prefer judge decisions over long judge essays.
- Evidence beats claims.
- The filesystem and git are truth.
- Obsidian owns broad knowledge; DevFlow owns active execution.
- The UI should show stage, artifact, blocker, evidence, and next action before dashboards or decorative status.
