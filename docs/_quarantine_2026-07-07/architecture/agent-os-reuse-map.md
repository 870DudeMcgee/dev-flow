# Agent OS Reuse Map

Status: Non-runtime research note
Date: 2026-06-04

## Purpose

Dev-Flow should not invent its operating model in isolation. The right strategy is to keep Dev-Flow's implementation centered on local filesystem state, isolated workspaces, verification evidence, and human promotion while borrowing proven Agent OS primitives from adjacent open-source projects.

This map covers the three highest-signal repos from the current research spike:

- [itseffi/agentic-os](https://github.com/itseffi/agentic-os)
- [KbWen/agentic-os](https://github.com/KbWen/agentic-os)
- [buildermethods/agent-os](https://github.com/buildermethods/agent-os)

The repos were cloned outside this checkout under `/tmp/devflow-agent-os-research/` for inspection. Do not vendor them into Dev-Flow without an explicit licensing and architecture decision.

This document is not runtime authority. It records reusable ideas only; commands, files, or workflows named here are not active Dev-Flow behavior unless they are also listed in [docs/control-room-mvp.md](../control-room-mvp.md) or a later active architecture contract.

## Fit Summary

| Source | License | Best Fit | UI Assets | Dev-Flow Use |
| --- | --- | --- | --- | --- |
| `buildermethods/agent-os` | MIT | Spec-driven product planning, standards discovery/indexing, standards injection, spec folder shape | None found | Borrow directly or adapt with attribution where useful |
| `KbWen/agentic-os` | MIT | Governance-first lifecycle, delivery gates, phase routing, work logs, token-aware loading, skill registry conventions | None found | Strongest direct source for DevFlow control-plane gates and lifecycle vocabulary |
| `itseffi/agentic-os` | CC BY-NC-SA 4.0 | Personal OS structure, backlog-to-task workflows, memory stack, session evals, cross-runtime wrappers | One banner image only | Use as inspiration/internal reference; avoid direct derivative code/docs in distributable DevFlow |

## Borrow Directly

These ideas are compatible with Dev-Flow's current product boundary and can be implemented as Dev-Flow-native modules.

### Spec Folder Shape

From `buildermethods/agent-os`, the strongest reusable structure is a feature spec folder that saves shaping work before implementation. Their shape-spec flow creates:

```text
agent-os/specs/<timestamp-feature>/
  plan.md
  shape.md
  standards.md
  references.md
  visuals/
```

Dev-Flow equivalent:

```text
.devflow/goals/<goal_id>/specs/<spec_id>/
  plan.md
  shape.md
  standards.md
  references.md
  visuals/
```

This maps cleanly onto the existing goal/task-slice model and should feed `devflow operating-layer` as a first-class "Spec Board" surface.

### Standards Index And Injection

`buildermethods/agent-os` separates standards discovery, indexing, and injection. Dev-Flow may later adapt that as a human-reviewed standards index under `.devflow/standards/`, but no standards-index CLI is active in the operating-layer slice.

The important pattern is the index: agents should not read every standards file. The UI should show which standards are attached to a goal, spec, task, or worker packet.

### Governance Lifecycle

`KbWen/agentic-os` has the strongest lifecycle vocabulary: bootstrap, spec, plan, implement, review, test, handoff, ship, with delivery gates and evidence requirements. Dev-Flow already owns task state and verification, so the reusable piece is not ceremony; it is the visible gate model:

```text
intake -> shape/spec -> plan -> run worker -> review evidence -> verify -> promote-preview -> promote/close
```

Dev-Flow should show this lifecycle in the operating layer as stage rails and gate receipts, not as mandatory old-style rituals.

### Work Logs And Gate Receipts

`KbWen/agentic-os` uses per-task work logs and gate receipts. Dev-Flow already has `events.jsonl`, `verification.json`, logs, and merge-readiness evidence. The direct adaptation is to add a derived "Gate Receipts" projection:

- intake complete
- plan/spec saved
- worker evidence present
- verification passed
- promotion preview fresh
- human decision recorded

This should be read-only at first and rendered from existing task artifacts.

### Session Evals

`itseffi/agentic-os` treats evals as session review artifacts. Dev-Flow already has dogfood scorecards and Knowledge Foundry. The useful adaptation is a lightweight task/milestone retrospective:

```text
.devflow/evals/<eval_id>/
  eval.md
  source_task_id
  findings
  reusable_knowledge_candidates
```

This should remain human-reviewed and separate from hidden memory.

## Adapt Into DevFlow Docs/Specs

These are valuable, but should be rewritten in Dev-Flow vocabulary rather than copied.

### Personal OS Memory Stack

`itseffi/agentic-os` frames the stack as instructions, goals, tasks, knowledge, skills, workflows, and evals. Dev-Flow's safer equivalent:

```text
Instructions: AGENTS.md and active docs
Goals: .devflow/goals/
Tasks: .devflow/tasks/
Workspaces: .devflow/workspaces/ or opt-in worktrees
Knowledge: .devflow/knowledge/
Skills/agents: registry profiles and manual packets
Evals: .devflow/dogfood/ and future .devflow/evals/
```

The operating layer should make this stack visible as navigation sections.

### Backlog Processing

`itseffi/agentic-os` has a strong backlog-to-task workflow with duplicate checks, clarification, and priority sorting. Dev-Flow may later design a preview-first backlog intake proposal, but backlog commands are not active in the operating-layer slice and should not be implemented from this research note.

### Task Classification

`KbWen/agentic-os` classifies tasks and selects workflow depth. Dev-Flow should add a deterministic classification projection before any routing runtime:

- tiny docs/update
- quick fix
- feature slice
- multi-module feature
- risky/security-sensitive
- research/spec-only

This should influence UI risk badges, suggested verification depth, and whether the task is AFK-safe or HITL, without autonomously routing models.

### Token-Aware Loading

Both Dev-Flow and `KbWen/agentic-os` care about context cost. Dev-Flow should keep its current token discipline and add UI visibility:

- standards attached
- context risk
- packet size estimate
- files included
- files intentionally excluded

This belongs in task packets and the task inspector.

## Ignore For Now

These conflict with current Dev-Flow boundaries or are too speculative for the operating-layer slice.

- Full AIOS kernel/runtime adoption from `agiresearch/AIOS`.
- Agent marketplaces, remote kernels, VM controllers, memory managers, or agent SDK ecosystems.
- Provider-backed autonomous routing.
- Mandatory phase ceremonies before ordinary work.
- Hidden memory or vector/RAG systems.
- Database-backed task state.
- Cron/autonomous unattended workflows.
- Cross-service personal assistant features such as email/calendar automation.
- Direct import of `itseffi/agentic-os` content into distributable Dev-Flow docs because its license is CC BY-NC-SA 4.0.

## UI Reuse Findings

No reusable app UI code was found in the three inspected repos:

- no `package.json`
- no React/Vite/Next app
- no `.tsx`/`.jsx`
- no CSS app shell
- no dashboard components

`itseffi/agentic-os` includes one banner image under `Resources/assets/`, but it is not useful for Dev-Flow's operational UI and has license constraints.

Conclusion: borrow the operating model, not UI code. Continue building Dev-Flow's UI over its own snapshot contract.

## DevFlow Implementation Direction

The operating layer should evolve in this order:

1. Read-only snapshot: already started as `devflow operating-layer snapshot --json`.
2. Local browser shell: serve the same snapshot without adding a database.
3. Spec Board: render goal specs, task slices, standards, references, and visuals.
4. Gate Receipts: render task lifecycle evidence as a compact checklist.
5. Standards visibility: keep references read-only until a separate standards-index contract is approved.
6. Backlog intake: keep as a future proposal, not an active command surface.
7. Evals: task/milestone retrospectives that can feed Knowledge Foundry after human review.

## Decision

Do not fork or vendor these repos as Dev-Flow runtime dependencies.

Use `buildermethods/agent-os` and `KbWen/agentic-os` as MIT-licensed sources for design patterns and possible small adapted snippets where appropriate. Use `itseffi/agentic-os` as inspiration only unless a future licensing decision explicitly allows broader reuse.
