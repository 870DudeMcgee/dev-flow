# DevFlow Source of Truth

Status: Active canonical direction
Date: 2026-07-07

This document is the active source of truth for DevFlow.

Older architecture, roadmap, cockpit, orchestration, local-worker, model-routing, and software-factory documents are absent from the active checkout. Recover historical material from the Git archive only when a human explicitly asks; it must never be loaded as active context by default.

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
| Hermes | Runtime/tool/messaging harness used by agents and workflows, not DevFlow's identity. The browser chat panel shares the brainstorm role with Hermes. |
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

Brainstorming happens in the browser's chat panel or in Hermes. Both surfaces
persist transcripts through the same brainstorm filesystem layer and create
pipeline runs at the idea stage. The operator picks which eligible model serves
the brainstorm role through the chat panel's model selector.

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

The browser status board is an auto-refreshing live feed. Any interactive UI
state on that page (selected worker output, expanded worker loop, open artifact,
collapsed worker loop, or nested scroll position) must survive refresh and must
not depend on a stable DOM node between refreshes. Defaults apply only until the
operator makes an explicit choice; refresh must not re-open, reset, or reselect
after that choice.

The browser is also the brainstorm surface. The chat panel on the right side of
the status board lets the operator start brainstorm conversations with any
eligible model in the registry. Chat sessions create pipeline runs at the idea
stage and persist transcripts through the same brainstorm filesystem layer that
Hermes uses. The chat panel's model selector determines which model serves the
brainstorm role; the selection persists per session. The composer offers browser
speech dictation when the current browser supports it and clearly reports when
dictation is unavailable.

Worker evidence must distinguish execution status from product outcome. A
finished model call or dispatch is not a successful result when its judge
failed, the loop exhausted its retry cap, or verification did not pass. The
status board presents active runs as a compact queue with exactly one focused
workspace. It leads with live model output while a role is running and a
plain-language product overview after completion: intent, rationale, scope,
changed files, result, verification evidence, and next action. Worker evidence
names the resolved model that actually served the call as well as its configured
route. Raw output, prompt/context, metadata, token budget, token usage, finish
reason, and built code remain available as secondary source evidence.

The focused workspace leads with a plain-language `Now` outcome and the next
safe action, followed by chronological `Activity`. Stage artifacts live in a
hidden `Files` drawer grouped by Idea, Specification, Plan, Build,
Verification, and other evidence; selecting a file opens its real contents.
Git and workspace identity remain in the primary header while secondary runtime
diagnostics live behind `System`. These presentation choices must not weaken
the underlying evidence, refresh persistence, or completed-run inspection.

Every launched run must have explicit ownership and control state. Operators
can request cancellation after the current role or stop the run-owned process
group immediately; neither action stops a shared model server. Incomplete role
events with no live owner become `stalled`, and stale local-model locks may be
reclaimed only after owner validation. Partial model output remains inspectable
after failure or cancellation.

Final acceptance is also gated by a persisted reliability report. Verification
receipts are immutable by receipt ID and carry local SHA-256 integrity
attestations. These detect accidental or single-file modification inside the
local trust boundary; they are not cryptographic proof against an attacker who
can rewrite both a receipt and its attestation. Within that stated boundary,
receipt tampering, unexpected routing changes, concurrent or replayed role
events, missing or out-of-fleet provider-served model identity, builder/reviewer
correlated model-family overlap, unresolved ownership, and provider faults beyond the recorded
threshold fail closed. Critical integrity or routing breaches recommend
rollback, while a validated dead-owner recovery records interrupted roles as
failed evidence before releasing ownership for an explicit retry. Receipts
created before this gate require an explicit operator-confirmed local-attestation
migration with an audit note; they are never silently trusted or discarded.

Builder work is file-producing, bounded, and isolated. A builder packet may
touch at most six declared files. Multi-file output must be a complete unified
diff, is checked before application, and is materialized in the pipeline run's
isolated workspace. The judge reviews the materialized change manifest, diff,
and verification receipt rather than treating a long model response as built
code. Frontier-provider adapters are verified with mocked transports during
local execution; local workers must not replace semantic API integration with
keyword matching.

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

Historical docs should be deleted from the active checkout after an archive reference is created. They are not default context.

## Canonical References

The following files may remain active when they are kept aligned with this source of truth:

- `AGENTS.md` — repo-specific agent operating rules.
- `README.md` — project entrypoint and user-facing summary.
- `docs/DEVFLOW_SOURCE_OF_TRUTH.md` — this document.
- `docs/local-worker-policy.md` — compact local worker boundary, if kept short and aligned.
- `docs/verification-ledger.md` — evidence history, if kept factual and non-prescriptive.

Any other document must earn active status by directly supporting the current loop. Otherwise archive it and delete it from the active checkout.

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
