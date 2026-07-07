# Dev-Flow Operator-Centered Mission

Status: Active product intent
Audience: all agents, workers, reviewers, and humans changing Dev-Flow
Related: [../PRODUCT_NORTH_STAR.md](../PRODUCT_NORTH_STAR.md), [control-room-mvp.md](control-room-mvp.md), [devflow-operating-model.md](devflow-operating-model.md)

---

## One-Sentence Mission

Dev-Flow is the operator's external executive-function system for turning an overwhelming flow of ideas into visible, prioritized, verified, buildable work without losing context, control, or trust.

Scope note, 2026-07-06: the broader command-center and durable knowledge surface now lives in Obsidian Command Center. Dev-Flow applies this mission as the selected-repo loop cockpit: it guides active repo execution while Obsidian owns broad capture, project context, daily context, parking lots, and cross-project knowledge.

---

## Why This Exists

The primary operator is extremely creative, adapts quickly, and generates far more ideas than can be held in working memory or built immediately. The operator also identifies as ADHD and slightly autistic. That is not a defect for Dev-Flow to "fix"; it is a design reality and a product advantage when supported correctly.

The product must assume:

- ideas arrive faster than they can be organized;
- attention can shift rapidly when a new possibility appears;
- dense text and hidden process state create friction;
- unclear next actions cause stalls, task switching, or rework;
- visual state and durable artifacts reduce cognitive load;
- unlimited idea capture is good, but unlimited active work is destructive;
- trust comes from evidence, not reassuring prose.

Dev-Flow exists to catch the creative firehose, make it visible, shape it into actionable artifacts, and move only the right work into execution.

---

## Product Identity

Dev-Flow is not merely a dashboard for coding agents.

It is a local-first control room that provides:

1. **Capture** — ideas, notes, questions, screenshots, brainstorms, and raw intent can be stored without forcing immediate organization.
2. **Triage** — raw material can be clustered, classified, scored, parked, promoted, or archived.
3. **Shaping** — promising ideas become brainstorms, specs, plans, tasks, and definitions of done.
4. **Execution** — workers operate in bounded task contexts with explicit identities, artifacts, logs, and permissions.
5. **Quality loops** — builder/judge/reviewer/verification gates improve and test output before promotion.
6. **Recovery** — failed, blocked, stale, and rejected states have visible reconciliation paths.
7. **Learning** — outcomes feed scorecards, routing rules, and process improvements.

The system should feel like:

> "My ideas are safe, my active work is constrained, and the next right action is obvious."

---

## The Human Gap Dev-Flow Must Bridge

Without Dev-Flow, the operator's natural loop can become:

```text
idea explosion
  -> excitement
  -> more ideas
  -> start one thread
  -> notice a tooling gap
  -> fix the tool
  -> open more loops
  -> scatter context across chats/files/logs
  -> lose the obvious next action
```

Dev-Flow must externalize this loop into:

```text
capture
  -> triage
  -> shape
  -> prioritize
  -> build
  -> judge
  -> verify
  -> ship / archive
  -> learn
```

The product succeeds when the operator can keep generating ideas at full speed while Dev-Flow protects active work from becoming chaos.

---

## Core Design Commitments

### 1. Capture must be zero-friction

Raw capture should not require project selection, perfect tags, priority, or a complete task description. Capture first; organize later.

Good capture surfaces:

- Telegram or chat message;
- quick browser input;
- CLI command;
- voice transcript;
- screenshot or pasted note;
- brainstorm transcript;
- worker/reviewer observation.

The capture layer should preserve raw input as evidence rather than overwrite it with a model summary.

### 2. Active work must be constrained

The operator may have unlimited ideas, but active execution must stay bounded.

A healthy default posture:

```text
unlimited raw ideas
limited candidates
limited active goals
tiny number of active builds
clear parking lot for everything else
```

Dev-Flow should make it easy to park good ideas without feeling like they are lost.

### 3. Every state needs a next action

A Dev-Flow item is incomplete if it has a state but no visible next action.

Examples:

| State | Required next-action choices |
|---|---|
| Raw idea | classify, ask clarifying question, park, archive |
| Candidate idea | promote to brainstorm/spec/goal/task, park |
| Spec ready | generate plan, edit spec, archive |
| Plan ready | create task, revise plan |
| Task ready | start worker, assign worker, close |
| Worker output exists | run quality loop, review patch, dry run, retry |
| Judge rejected | return to builder, ask human, park |
| Verification failed | root-cause debug, retry, abandon |
| Blocked | answer question, unblock, abandon |
| Failed | retry with a different worker/model, close as abandoned |
| Verified | promote, archive, request human review |

No dead-end screens. No empty command boxes as the primary action. No hidden knowledge required to continue.

### 4. Visual state is not decoration

Color, badges, lanes, and hierarchy are core functionality. The operator should be able to glance at the control room and know what matters.

Recommended semantic colors:

| State | Visual treatment |
|---|---|
| Raw / unprocessed | gray |
| Needs clarification | purple |
| Candidate / shaped | blue |
| Running / active | cyan |
| Blocked / waiting | orange |
| Failed / rejected | red |
| Ready to verify | yellow |
| Verified | green |
| Promoted / shipped | solid green with check |
| Parked / safe later | muted blue-gray |
| Abandoned / closed | dark gray |

If the user has to read paragraphs to know which item needs attention, the UI is failing.

### 5. Evidence beats confidence

Agents must not report completion based on intent, plan, or plausible prose.

Acceptable evidence includes:

- created artifact path;
- diff or patch;
- command output;
- test output;
- verification JSON;
- review report;
- screenshot or visual check;
- state transition record;
- model run record;
- scorecard/eval result.

Unacceptable completion language:

- "it should work now";
- "the implementation is complete" without evidence;
- "I added the logic" without showing what changed and how it was verified;
- "looks good" without a review basis.

### 6. Roles must stay separated

One chat/model should not silently act as architect, implementer, reviewer, judge, verifier, and historian at once.

Dev-Flow should keep these roles explicit:

| Role | Job | Should not do |
|---|---|---|
| Architect | shape system direction and tradeoffs | silently edit code |
| Planner | create small ordered tasks | improvise scope mid-execution |
| Worker | execute one bounded task | redefine the product goal |
| Spec reviewer | check whether work matches the spec | grade general style first |
| Quality reviewer | check maintainability, security, tests | accept spec gaps |
| Judge | score output against definition of done | be the same unchecked builder |
| Verifier | run tests/checks and record evidence | trust generated claims |
| Historian | preserve decisions and reusable lessons | create hidden state only |

### 7. Local-first sovereignty matters

Dev-Flow should preserve the operator's preferred model posture:

```text
local models for heavy routine work and private context
cheap cloud models for routing, planning, and lightweight advisory work
expensive/frontier models for hard audit, architecture, and escalation
```

Do not turn Dev-Flow into a system that requires an always-on SaaS backend or opaque cloud autonomy to remain useful.

---

## Canonical Pipeline

The product's main idea-to-execution path is:

```text
Idea
  -> Brainstorm
  -> Spec
  -> Plan
  -> Task
  -> Worker
  -> Builder-Judge / Review Loop
  -> Verify
  -> Promote
  -> Eval / Learn
```

Each arrow is a product contract. A stage is not complete unless it produces both:

1. a durable artifact, and
2. a visible next action.

Examples:

- Brainstorm must lead to spec generation or parking.
- Spec must lead to planning or explicit revision.
- Plan must create a task with implementation context.
- Task creation must show worker buttons, not a blank shell input as the main path.
- Worker output must feed quality/review/patch gates.
- Passed review must expose verification.
- Passed verification must expose promotion or archive.
- Promotion should feed outcome learning and model/process scorecards.

---

## Idea Foundry / Greenhouse Direction

Idea Foundry is the root support layer for the operator's creativity. It now has a first visual operating-layer slice, Idea Greenhouse V1, for raw and maturing ideas, and it should continue to evolve from there.

Expected lanes:

```text
Raw -> Clarify -> Clustered -> Candidate -> Promoted
                 \-> Parked
                 \-> Archived
```

The current V1 keeps capture local under `.devflow/ideas/`, supports non-destructive parking without losing raw evidence, and keeps promotion as an explicit human decision. V1 does not run models, cluster ideas, or auto-create tasks/goals.

The greenhouse should continue toward:

- instant capture;
- duplicate/similar idea grouping;
- AI-assisted classification;
- energy / leverage / feasibility / strategic-fit scoring;
- daily or on-demand idea digest;
- promotion into brainstorm/spec/goal/task;
- safe parking without losing the idea;
- archive/reject with rationale.

Important distinction:

```text
Creativity is unlimited.
Active execution is constrained.
```

---

## Daily / Session Focus Direction

Dev-Flow should eventually answer, at the start of a session:

```text
What is active?
What is stuck?
What changed since last time?
What new ideas arrived?
What is the strongest next action?
What should be parked or closed?
```

A useful focus digest should contain:

- one recommended primary build/action;
- top new candidate ideas;
- blocked/failed tasks needing reconciliation;
- verification/promote opportunities;
- warning if active work exceeds WIP limits;
- links to evidence, not just summaries.

---

## Agent Instructions

When an agent works on Dev-Flow, it should optimize for operator clarity, not just feature completion.

Before changing behavior, ask internally:

1. Does this reduce or increase cognitive load?
2. Does it preserve raw evidence?
3. Does it make state more visible?
4. Does every resulting state have a next action?
5. Does this constrain active work while preserving unlimited capture?
6. Is the model/worker identity visible wherever work happens?
7. Is failure recoverable and understandable?
8. Is there verification evidence?
9. Is this local-first and bounded unless explicitly approved otherwise?
10. Does the full user journey work end-to-end, not just one component?

### End-to-end walkthrough requirement

For multi-stage features, do not stop at unit/component success. Walk the user journey:

```text
entry point -> action -> artifact -> next visible state -> next action -> terminal outcome
```

If the journey ends at an empty input, generic placeholder, hidden command, or unexplained state, the flow is broken.

---

## Anti-Patterns

Avoid these even when the code technically works:

- building a feature that creates an artifact but no next action;
- adding hidden automation that is not reflected in task state/evidence;
- exposing raw shell command boxes as the primary path for non-expert flows;
- scattering one decision across chat, docs, task files, and logs without a canonical artifact;
- treating model output as verified work;
- using a stronger model to compensate for a weak task packet or missing definition of done;
- requiring the operator to remember where work left off;
- adding broad autonomy before visual state, recovery, and verification are reliable;
- creating more active lanes without parking/archival paths;
- designing for generic enterprise users before solving the primary operator's real workflow.

---

## Success Criteria

Dev-Flow is working when:

- ideas can be captured immediately and safely;
- the operator can see the whole system state at a glance;
- the UI always offers one clear primary next action;
- good ideas can mature without becoming urgent tasks;
- active work is limited and visible;
- failed work has retry/abandon/escalate paths;
- workers produce evidence, not mystery changes;
- quality gates improve output before verification;
- verification and promotion are explicit;
- model choices are measured and routable;
- the operator feels less scattered, not more burdened.

The emotional target is calm control over high creative throughput.

---

## Short Version For Agents

If you remember only one thing:

> Dev-Flow exists to help a highly creative, neurodivergent operator convert a flood of ideas into visible, prioritized, verified work. Preserve unlimited capture, constrain active execution, show state visually, provide the next action, and never claim completion without evidence.
