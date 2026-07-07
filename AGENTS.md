# Dev-Flow Agent Guide

Global Codex session behavior is defined by
`/Users/jewelbait/.codex/session-operating-contract.md`. Read that file first.
This repo guide adds DevFlow-specific product, verification, and safety details;
it does not replace the global session contract.

DevFlow is the local operating layer for turning rough ideas into verified product implementations. It owns the active product-building loop: definition, spec, planning, plan review, bounded delegation, builder/judge execution, evidence-backed verification, and the next human decision.

Product authority lives in [docs/DEVFLOW_SOURCE_OF_TRUTH.md](docs/DEVFLOW_SOURCE_OF_TRUTH.md). Read it when shaping product direction, UI flows, idea intake, worker orchestration, or any feature that affects cognitive load. Quarantined and deleted historical docs are recovery material only; do not load them as active context unless the human explicitly asks.

Local checkout note: use `<repo-root>` for portable command examples. This checkout is referred to as `DevFlow` in docs and handoffs.

Use this file after the global session contract to start useful DevFlow work
quickly without spending frontier context on repository archaeology.

## Session Contract

Follow `/Users/jewelbait/.codex/session-operating-contract.md` for session
start, orientation, Agent Proxy use, local fleet routing, and session closeout.

DevFlow's closeout command is:

```bash
scripts/session-freshness-closeout.sh /Users/jewelbait/Desktop/Local\ AI\ Dev\ Team
```

## DevFlow Fleet Routing

Use `/Users/jewelbait/.codex/session-operating-contract.md` for active local
fleet routing, lane roles, ports, swap behavior, Agent Proxy use, and closeout.
The repo files [docs/fleet-debrief.md](docs/fleet-debrief.md) and
[.devflow/fleet-contract.json](.devflow/fleet-contract.json) are supporting
evidence only.

### What tool to use for code work

| Task | Tool | LLM needed? |
|---|---|---|
| Module-level function extraction (refactoring) | `extract_module.py` | No — deterministic |
| Test + lint verification | `local_test_runner.py` | No — wrapper script |
| Codebase survey / seam analysis | `codebase_survey.py` | Yes (Ornith 35B) |
| Code generation (new code, not extraction) | builder-judge-loop.sh | Yes (Ornith 35B builder + Qwen 27B judge) |
| Context compression | `compress_tool_output.py` | Yes (Ornith 35B) |

Scripts live in `~/.hermes/skills/software-development/local-fleet-efficiency/scripts/`.

## Default Workflow

Follow `/Users/jewelbait/.codex/session-operating-contract.md` for the default
Codex workflow. DevFlow-specific loop commands may return task packets with
`files_to_touch`, `tests`, `risks`, `recommended_lane`, `verification`, and
`context_brief`; the frontier reads those compact packets instead of broad raw
source.

## Handoff Format Standard

Do not create handoff docs by default. Follow the documentation discipline in
`/Users/jewelbait/.codex/session-operating-contract.md`: update existing
authority files first, use task/state artifacts or the final response for
routine continuation notes, and create a new handoff only when the human
explicitly asks for one.

When a handoff is explicitly requested, it must follow this shape. Do not add
workflow instructions, tool routing, or fleet config. The handoff provides only
task-specific details.

```markdown
# DevFlow Refactor — Handoff (Slice X)

## State
- Committed: <hash>
- Tests: <N> passing
- Fleet: see AGENTS.md

## Task
<2-3 sentences describing what to do>

## Target files
- <list of files to create or modify>

## Commands
<exact commands — map, compress, route, verify — no prose instructions>

## Constraints
- Follow AGENTS.md workflow
- Use local_test_runner.py for verification
- Do not push without approval
```

Handoffs must not override the workflow. The orientation rule always applies.
If a task is genuinely tiny, do not create a handoff unless the human asks.

## Current Product

Dev-Flow is not an autonomous software factory and not the coding intelligence itself. It is the operational layer around replaceable workers.

It owns:

- tasks and isolated workspaces
- locks and ownership
- worker/model identity
- status, questions, logs, reports, and evidence
- verification and merge readiness
- explicit close, cleanup, retry, and promotion controls

The current browser product is the operating layer served by:

```bash
source .venv/bin/activate
devflow operating-layer serve
```

If the `devflow` console script is not installed in the active venv, use the module entrypoint:

```bash
env PYTHONPATH=src:. .venv/bin/python -m devflow.cli operating-layer serve
```

The canonical UI title is `Dev-Flow Operating Layer`. The first viewport should expose the real control-room workbench: `Brainstorm`, `Pipeline`, `Worker lanes`, `Review queue`, and `Evidence stream`. The deleted root `public/` static surface is not the active product UI and must not be used for validation.

## Product Experience To Protect

The UI is close to the desired shape. Improvements should make it easier for the operator to start work without babysitting every small step while still knowing exactly what is happening.

In particular:

- `Create task` should create a real Dev-Flow task, show the new task clearly, and offer the next executable action.
- Any model or worker used by Brainstorm, orchestration, patch proposal, review, or execution must be named in the UI.
- If system health says tasks are active, the UI must make those tasks visible with title, status, worker/model, last update, and next action.
- Worker lanes, review queue, and evidence stream should show concrete task/log/evidence data, not vague summaries.
- Current tasks need useful controls: inspect, run/start when eligible, verify, retry, close, cleanup preview/apply where supported, and promote when safe.
- Automation is welcome when it is Dev-Flow-owned, logged, bounded, and gated. Invisible orchestration is not welcome.

## Automation Posture

The direction is aggressive local automation with hard stops:

- automate routine Dev-Flow loops where policy and command flags allow it
- prefer shell workers and existing verified task/loop machinery for code-changing work
- keep provider/model runs as explicit evidence or patch-proposal lanes unless a later runtime contract promotes them
- preserve human-readable evidence for every automated action
- do not push, publish, open PRs, or perform broad promotion without explicit human approval

Future architecture is valuable and should remain in `docs/architecture/` or clearly marked roadmap docs. It is not startup authority for ordinary UI/product fixes unless the task is specifically about that future layer.

Hyperplane is quarantined as experimental evidence infrastructure. Do not use it for first-pass model validation or fail-fast smoke tests; it expands into a dynamic multi-call evaluation pipeline. Prefer direct, bounded one-target-call/one-judge-call smoke evidence until a separate task explicitly reopens Hyperplane.

## Local Worker Policy

Local worker policy is defined by
`/Users/jewelbait/.codex/session-operating-contract.md`.

In Codex sessions, gather evidence with Context Map, Agent Proxy, Graphify, and
deterministic scripts; then route bounded build or judge packets through the
active Ornith/Qwen workflow.

Passive MCP fleet telemetry should stay disabled unless the current session
needs that operator surface. Active smoke completions are decision-point proof,
not routine inventory.

The concise current policy lives in [docs/local-worker-policy.md](docs/local-worker-policy.md).

## Where To Work

Active control-room implementation belongs in:

```text
src/devflow/control_room/
tests/
docs/
```

Top-level `src/devflow/*.py` files should stay limited to package/CLI entrypoints and explicit bridges into `src/devflow/control_room/`.

## Working Rules

For ordinary fixes:

1. Run the mandatory orientation step.
2. Read this file and any named handoff/skill.
3. Route mapping, compression, implementation, and judging through the approved local tools/workers.
4. Make direct edits only for plans, authority docs, or tiny activation glue unless a fallback is recorded.
5. Run verification scaled to the risk.
6. Report what changed, what passed, and what remains risky.

Only expand into broader docs when the task actually needs them:

- Active source of truth: [docs/DEVFLOW_SOURCE_OF_TRUTH.md](docs/DEVFLOW_SOURCE_OF_TRUTH.md)
- Active docs index: [docs/README.md](docs/README.md)
- Verification reuse: [docs/verification-ledger.md](docs/verification-ledger.md)
- Historical recovery only: [docs/_quarantine_2026-07-07/](docs/_quarantine_2026-07-07/)

Do not load quarantined architecture, roadmap, cockpit, orchestration, local-worker, model-routing, or software-factory docs as active context unless the user explicitly asks for historical recovery.

For major architecture cleanup, use Graphify as generated evidence. Start from `graphify-out/GRAPH_REPORT.md` and `graphify-out/Dev-Flow-callflow.html`, record metrics in a lightweight doc or handoff, and rerun Graphify after the cleanup milestone. Do not treat generated Graphify output as product authority or blindly commit the full `graphify-out/` directory.

## Git And Worktree Safety

There may be unrelated user or agent changes in the worktree. Do not revert work you did not make.

When `.devflow/` exists, prefer Dev-Flow git commands where they work:

```bash
devflow git status
devflow sync-main
devflow task promote-preview <task_id>
devflow task promote <task_id>
devflow push-main
```

If the console script is unavailable, use:

```bash
env PYTHONPATH=src:. .venv/bin/python -m devflow.cli git status
```

Do not run raw `git push origin main`, raw promotion merges, or conflict-resolution rebases unless the human explicitly authorizes it.

## Verification Policy

- Documentation-only changes: run `git diff --check` and a targeted stale-context search.
- Focused code changes: run targeted tests around touched behavior.
- Operating-layer UI changes: run targeted operating-layer tests and, when practical, validate the served UI with a cache-busted browser URL.
- Full pytest and dogfood are release/broad-change gates, not the default for every small fix.

Use [docs/verification-ledger.md](docs/verification-ledger.md) before rerunning expensive verification.

## Communication

Keep updates concise and useful. Avoid narrating every internal rule check, but do speak up for blockers, verification failures, or risks that change the next safe action.

Completion reports should use the standard handoff headings from [docs/handoff-template.md](docs/handoff-template.md) when the task is more than a tiny answer:

```text
## Status
## Outcome
## Files Changed
## Verification
## Risks
## Recommended Next Steps
## Next Safe Action
```
