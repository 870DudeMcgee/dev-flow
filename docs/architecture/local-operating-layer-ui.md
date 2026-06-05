# Local Operating-Layer UI

Status: Active implemented control-layer slice
Date: 2026-06-04

## Purpose

Dev-Flow needs an operating layer that lets the user see and organize parallel AI coding work without reading raw logs or trusting hidden agent memory.

This is not a new coding agent. It is a local-first control surface over the state Dev-Flow already owns:

- goals and specs
- task slices
- isolated workspaces and worktrees
- worker ownership
- questions and blockers
- task events and logs
- verification evidence
- promotion readiness
- multi-project status

The filesystem remains the source of truth. The operating layer is a derived projection.

Related reuse guidance lives in [docs/architecture/agent-os-reuse-map.md](agent-os-reuse-map.md). That map says Dev-Flow should borrow Agent OS operating-model primitives, not vendor a different runtime or dashboard wholesale.

## Research Signals

The useful Agent OS patterns are consistent across current agent tools:

- Agent OS emphasizes product planning, spec shaping, spec writing, task creation, implementation, and orchestration as a repeatable spec-driven cycle: https://buildermethods.com/agent-os/v2/workflow
- Agent OS concepts separate reusable standards from task skills and keep the structure file-backed and inspectable: https://buildermethods.com/agent-os/concepts
- OpenAI frames the Codex app as a command center for agents: multi-agent work is organized by projects/threads, worktrees isolate concurrent work, and the user can review changes, comment, or open work in an editor before integration: https://openai.com/index/introducing-the-codex-app/
- OpenAI's original Codex cloud-agent launch highlights the evidence contract Dev-Flow should preserve: each task runs independently, progress is monitorable, terminal logs and test outputs cite what happened, and human review remains required before integration: https://openai.com/index/introducing-codex/?video=1084810944
- Claude Code worktree docs make isolation a first-class parallel-work primitive: separate working directories and branches prevent concurrent sessions from touching each other's files, while cleanup and local config copying are explicit workflow concerns: https://code.claude.com/docs/en/worktrees
- GitHub Copilot cloud agent makes background work transparent through plans, branches, logs, tests, and reviewable code changes before PR creation: https://docs.github.com/en/copilot/concepts/agents/cloud-agent/about-cloud-agent
- Linear for Agents keeps the human accountable while agents contribute work and status inside a visible issue surface: https://linear.app/agents
- LangGraph Studio and OpenAI Agents SDK tracing show the value of run observability, traces, replay/debug surfaces, and structured event inspection: https://docs.langchain.com/langsmith/observability-studio and https://openai.github.io/openai-agents-python/tracing/
- OpenAI's agent-building guide treats guardrails, tool risk, and human intervention as production requirements: https://cdn.openai.com/business-guides-and-resources/a-practical-guide-to-building-agents.pdf
- Claude Code subagents show the concrete UX value of role-specific agents, tool allowlists, hooks, lifecycle events, and worktree isolation: https://code.claude.com/docs/en/sub-agents

The referenced YouTube URL could not be fetched reliably during this spike because YouTube throttled online transcript access. Treat direct video-layout claims as user-supplied visual direction; the durable architecture conclusions above come from primary docs and the current rendered Dev-Flow screenshots.

## Agent OS Requirements

The operating layer should make Dev-Flow feel like an Agent OS without becoming another agent runtime. The useful requirements are:

1. **Command-center first viewport.** The first screen must answer: what is the current directive, what output just happened, what is the next safe action, and which worker lanes are moving or stuck?
2. **Human accountability stays visible.** Questions, blockers, promotion decisions, and unsafe actions must surface as explicit human-decision items instead of being hidden behind autonomous routing.
3. **Parallelism is organized, not theatrical.** Actual Dev-Flow workers should be shown as compact activity rows with plain state, task counts, verification/evidence state, and recent output volume. Decorative radar, abstract animation, and invented worker personas are not acceptable as the primary worker-status surface.
4. **Specs and standards are inspectable context.** Goals, specs, standards, references, and task packets must be visible enough for a human to understand why a worker is doing something without loading huge logs.
5. **Evidence beats trust.** Every worker outcome should connect to task events, log paths, verification evidence, readiness evidence, and safe next commands.
6. **Isolation is a product feature.** Workspace/worktree ownership, dirty state, branch state, and promotion readiness are not implementation details; they are control-room UI facts.
7. **Progressive disclosure protects attention.** Worker detail, lower boards, logs, and evidence panes should stay compact until the user drills down.
8. **The browser shell is guarded, not decorative.** It may execute supervisor-classified read-only Dev-Flow commands from the Action Rail, while mutating worker/runtime/task/git commands stop at an explicit approval gate and trusted CLI execution.

## Product Map

```text
Human intent
  -> Orchestrator command center
  -> goal / spec / standards context
  -> task-slice board
  -> parallel-lane planner
  -> isolated worker execution layer
  -> worker activity summary
  -> mission feed / evidence / logs / diffs
  -> verification layer
  -> promotion-readiness layer
  -> human decision layer
```

Current Dev-Flow mapping:

```text
Orchestrator       operating_layer.py snapshot, operating_layer_assets.py UI
Goal/spec          .devflow/goals/, goal_projection.py, goal_tasks.py
Standards/context  future .devflow/standards/index.yml, task_packet.py
Task board         task.yaml, status_projection.py, dashboard.py
Parallel lanes     freshness.py, freshness_runner.py, parallel_worker.py
Workers            shell_worker.py, worker_adapter.py, local model evidence wrappers
Isolation          workspace.py, worktree.py, branch.py, promotion.py
Evidence           events.jsonl, logs/, verification.json, WorkerEvidence
Review             review_capsule.py, promotion.py, readiness.py
Multi-project      project_registry.py, multi_project_freshness.py
```

## Options Compared

| Option | Shape | Strength | Risk | Decision |
| --- | --- | --- | --- | --- |
| Kanban-first dashboard | Lanes dominate first viewport; Orchestrator is secondary | Familiar task-management pattern | Hides the actual directive/output and makes agent OS feel like a generic board | Reject as primary layout |
| Chat-first command center | Thread/output dominates; boards are secondary | Matches agent collaboration surfaces | Can obscure parallel state if telemetry is not compact | Use as part of Orchestrator-first layout |
| Orchestrator-first control room | Directive, next action, mission feed, and actual worker activity dominate first viewport | Best match for supervising parallel AI work without reading logs | Requires disciplined progressive disclosure to avoid visual noise | Recommended |

## Recommended Direction

Dev-Flow should be an Orchestrator-first local control room:

- Overview page: project-wide `Worker Activity` grouped by real `task.worker` values, `Current Directive`, `Next Safe Action`, `Work Feed`, `System Health`, compact counters, and compact repository/project chrome.
- Drilldown pages: Workers, Goals, Specs, Progress, Alerts, Projects, Inbox, Actions, Evidence, and Review each show only the panels that belong to that work mode.
- Navigation: the browser shell uses hash-based page routing over one derived snapshot. Page changes must not spawn workers, mutate canonical state, or require a server-side route.
- Controls: Action Rail execution is limited to supervisor-classified `pure_read_only` Dev-Flow commands. Approval-required worker/runtime/task/git commands are displayed as explicit approval gates and are not executed by the browser.

## UI Spec

The operating layer should expose these reader-facing sections:

- Orchestrator: current directive, next safe action, work feed, system health, queue/ready/blocked/evidence counters, and project-wide worker activity grouped by actual Dev-Flow worker ids.
- Command Center: active project, branch, clean/dirty state, task health, and compact repo controls below the Orchestrator.
- Operating Map: page-level summary cards for goals, inbox, workers, progress, review, and projects.
- Goals: goal state, all projected task slices, linked task ids, risk, recommendations, blockers, next safe action, and projected parallel-safe batches.
- Worker Lanes: running, blocked, failed, needs-verification, ready-for-review, and idle tasks grouped for scanning.
- Task Inspector: task identity, workspace, owner, latest event, log pointers, verification, changed files, and safe next commands.
- Evidence Timeline: append-only task events, worker evidence, verification runs, and review-preview evidence.
- Question Inbox: human-input requests and blocked manual-worker questions.
- Ready for Review: verified work, merge readiness, review blockers, and preview commands.
- Multi-Project Overview: registered projects, health summaries, stale/missing project warnings, and next safe action per project.

First-viewport acceptance requirements:

- Orchestrator appears before repository chrome at desktop and mobile sizes.
- The old decorative radar is replaced by project-wide worker-activity rows that use plain names such as "Shell worker", "Qwopus implementer", and "Gemma reviewer" when those are the recorded task workers.
- Mobile shows directive/output before the worker activity stack.
- No horizontal overflow at desktop or mobile sizes.
- Screenshot QA is required for every visual repair, not just DOM checks.
- Non-overview panels must not remain stacked below the Overview page; they should be reachable through navigation as separate page views.

## Snapshot Contract

The operating-layer entrypoints are:

```bash
devflow operating-layer snapshot --json
devflow operating-layer serve --host 127.0.0.1 --port 8765
```

The snapshot must:

- read only existing Dev-Flow artifacts
- call existing projection modules instead of re-parsing state ad hoc
- include a schema version
- include project identity and health
- include goals and focus goal
- include task lanes
- include questions
- include review candidates from the existing promotion-readiness projection
- include evidence pointers, not copied evidence blobs
- include project-wide worker activity derived from actual recorded `task.worker` values
- include a plain-language mission feed derived from inbox items, questions, review readiness, task progress, task events, and evidence pointers
- include safe next actions
- include a Spec Board derived from goal/spec/task-slice artifacts
- include Progress page readiness checklists derived from task evidence and readiness artifacts
- degrade cleanly when freshness snapshots or optional artifacts are absent

The snapshot must not:

- create a database
- start a daemon
- call provider APIs
- route workers
- spawn workers
- verify tasks
- approve, merge, push, or open PRs
- mutate canonical task, goal, or project state

## Implemented Surface

The current local operating layer is the browser control layer and JSON snapshot over existing Dev-Flow projections. It is implemented under `src/devflow/control_room/` and wired through `devflow operating-layer`.

Implemented pieces:

- `operating_layer.py`: composes project health, goals, lanes, tasks, questions, inbox items, evidence pointers, freshness, spec board, task-progress receipts, multi-project status, worker activity, mission feed, action rail, and goal board into schema version 1.
- Worker activity projection: `operating_layer.py` derives project-wide worker rows with worker id, plain display name, state, task count, verified percent, recent output count, and latest task evidence.
- Mission feed projection: `operating_layer.py` derives plain-language Orchestrator updates such as "Task progress", "Task update", "Evidence", "Question", and "Ready for review" from existing Dev-Flow artifacts; the browser shell only renders this list.
- Work Feed and Workers pages: browser rendering translates raw event names, cleanup markers, lane states, and task statuses into plain-language status cards while keeping evidence paths and command previews available in drilldowns.
- `operating_layer_server.py`: serves `/`, `/api/snapshot`, `/api/actions/run`, `/app.css`, `/app.js`, and `/healthz` while keeping HTTP behavior separate from UI payloads and suppressing harmless disconnected-client tracebacks.
- Action execution: `/api/actions/run` classifies the requested command with the supervisor policy, executes `pure_read_only` Dev-Flow commands through a bounded local subprocess, caps output, and returns approval-gate JSON for unsafe commands. The only approved browser mutation is exact human-approved task verification: `devflow task verify <task_id> --shell "<command>"`, with the server rechecking the classifier, requiring the exact approval phrase, and refusing placeholder verification commands.
- Verification refresh: after an executed approved task-verification action, the browser re-fetches `/api/snapshot` so task lanes, status, progress receipts, and evidence panes update from filesystem truth without a manual page reload.
- `operating_layer_assets.py`: owns the bundled HTML, CSS, and JavaScript for the local browser shell.
- Orchestrator-first UI: renders current directive, next safe action, mission feed, health bars, counters, and real project-wide worker activity before repo chrome.
- Page routing: the browser shell maps hash navigation to separate page views so Overview, Workers, Goals, Specs, Progress, Alerts, Projects, Inbox, Actions, Evidence, and Review are not stacked into one cluttered page. The command center remains visible on routed pages so the global filter and project controls stay available.
- Project drilldown: `/api/snapshot?project=<project_id>` resolves registered projects through the existing registry and returns that project's derived snapshot.
- Global filter: narrows visible worker-lane tasks and Progress readiness receipts client-side by task id, title, status, worker, workspace, verification state, and latest event text without changing canonical state.
- Operating Map: scoped map nodes for goals, inbox, workers, progress, review, and projects.
- Selection Context Bar: names active map/goal scope and provides a Clear control.
- Action Rail: supervisor-classified commands for project, task, goal, lane, and batch contexts, with a collapsible command preview, read-only command execution, approval-gated task verification, bounded command output, and explicit approval gates for unsafe commands.
- Question & Blocker Inbox: groups manual worker questions, blocked tasks, failed/attention tasks, and freshness findings needing human decisions.
- Goals page: shows goal loop state, completion progress, all projected slices, linked task ids, risk, recommendations, ready/blocked lanes, conflict-aware parallel/worker/verification batches, and safe commands.
- Spec Board references: shows goal-specific relevant files, optional `.devflow/standards/index.yml` entries, and architecture contract links as bounded read-only reference chips.
- Task Inspector and Evidence Detail: selected task or goal context shows status, verification, recent events, evidence paths, scrubbed previews, task-progress summaries, and linked task evidence.
- Progress page: shows task-readiness summary counters and a per-task checklist for intake, worker output, verification, review preview, and human decision, with task status, worker, lane, latest update, and next safe command.
- Evidence Timeline: compact evidence pointers and filtered evidence when a scope is selected.
- Multi-Project Overview: registry-backed project health cards and project drilldown.
- Accessibility polish: focus-only skip link, keyboard focus styles, ARIA state for selected map/goal controls, live scope updates, and Escape-to-clear active scope.

Current verification for this surface lives in `tests/test_operating_layer.py`, plus broader control-room boundary tests.

## Implementation Plan

1. [x] Add `src/devflow/control_room/operating_layer.py` as a read-only composition module.
2. [x] Add `devflow operating-layer snapshot --json`.
3. [x] Lock the snapshot shape with focused tests.
4. [x] Add `src/devflow/control_room/operating_layer_server.py` as a local static browser shell that consumes the same snapshot contract.
5. [x] Add task inspector and evidence timeline panes.
6. [x] Add goal/parallel-lane and ready-review panes.
7. [x] Add Agent OS-inspired Spec Board and Task Progress projections without adding canonical state.
8. [x] Add Multi-Project Overview from the existing registry-backed dashboard projection.
9. [x] Add read-only project drilldown by resolving registered project ids through the existing project registry and fetching that project's derived snapshot.
10. [x] Add an Action Rail that lists supervisor-classified project, task, goal, lane, and batch commands without executing mutations.
11. [x] Add selected-task evidence drilldown with bounded recent events, verification summary, evidence paths, and scrubbed text previews.
12. [x] Add a Question & Blocker Inbox that groups manual questions, blocked tasks, failed/attention tasks, and freshness human-decision findings.
13. [x] Add Operating Map, scoped panel filtering, context reset, and accessibility affordances.
14. [x] Add polished Agent OS-style UI chrome with Orchestrator-first ordering, compact repo chrome, collapsible lower sections, attention strip, micro-interactions, and reduced-motion support.
15. [x] Split static UI assets into `operating_layer_assets.py` so the HTTP server remains a small request router.
16. [x] Add standards/reference visibility to the Spec Board from goal context, optional `.devflow/standards/index.yml`, and architecture contracts.
17. [x] Add command preview for Action Rail items.
18. [x] Add a client-side global filter for worker-lane task discovery.
19. [x] Replace decorative radar with real worker-activity rows and verify the first viewport with desktop/mobile screenshots.
20. [x] Move project-wide worker activity into a typed backend snapshot projection.
21. [x] Move the Orchestrator mission feed into a typed backend snapshot projection with plain-language labels.
22. [x] Split the long stacked dashboard into hash-routed page views using the same read-only snapshot.
23. [ ] Split large UI asset strings into deeper, efficient modules once the visual direction is accepted.
24. [x] Add explicit supervisor-safe Action Rail execution for `pure_read_only` Dev-Flow commands while blocking approval-required commands in the browser.
25. [x] Add the first approval-gated browser mutation for exact `devflow task verify <task_id> --shell "<command>"` commands, with server-side classifier recheck and exact approval echo.
26. [x] Refresh the browser snapshot after approved task verification so lane/status/evidence changes are visible immediately from `/api/snapshot`.

## Next Safe Slice

Prepare the next implementation slice around operational controls and maintainability:

1. Extract UI asset generation into focused Python functions or separate asset constants while keeping `operating_layer_server.py` as a small router.
2. Add visual-regression QA helpers that capture desktop/mobile screenshots and assert no overflow, Orchestrator-first ordering, progress rows, and no mission-feed overlap.
3. Review the full operating-layer diff for accidental scope creep.
4. Keep all active docs aligned with the guarded control-layer contract.
6. Run focused and broader verification.
7. Stage/commit only after human approval.

Do not add worker execution, promotion, git publication, or broad mutation buttons to the browser shell as part of this checkpoint. The only approved browser mutation is task verification through the guarded `/api/actions/run` approval path.

## Design Constraints

- Keep deep module boundaries: projection logic in `operating_layer.py`, CLI wiring in `cli.py`, browser serving later in a separate module.
- Reuse existing Pydantic models and projection functions where possible.
- Keep task evidence as pointers and compact summaries.
- Use deterministic, stable lane names so tests and future UI components can rely on them.
- Prefer commands as safe next actions over direct mutations.
- Do not weaken existing verification, promotion, lock, or workspace-isolation gates.
