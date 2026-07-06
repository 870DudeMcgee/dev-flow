# Dev-Flow Agent Guide

Dev-Flow is a local-first control room for AI coding workers. It should automate as much routine work as it safely can while keeping task state, worker identity, evidence, verification, and promotion visible to the human operator.

Dev-Flow's operator-centered mission is documented in [docs/operator-centered-mission.md](docs/operator-centered-mission.md). Read it when shaping product direction, UI flows, idea intake, worker orchestration, or any feature that affects cognitive load. The short version: Dev-Flow exists to help a highly creative, neurodivergent operator convert a flood of ideas into visible, prioritized, verified work. Preserve unlimited capture, constrain active execution, show state visually, provide the next action, and never claim completion without evidence.

Local checkout note: use `<repo-root>` for portable command examples. This checkout is referred to as `DevFlow` in docs and handoffs. The old local path `/Users/jewelbait/Desktop/DevFlow` is quarantined and must not be used for current work.

This file is the first-read instruction surface for agents. Use it to start useful work quickly. Do not turn every task into a repository archaeology pass.

## Fleet Routing (read this first)

Three local models, one heavy at a time. The model-router handles swaps.

| Port | Model | Role | Key property |
|---|---|---|---|
| 8084 | Qwen3-Coder-Next (80B-A3B, IQ4_XS) | Builder/coder | Non-thinking, 256K ctx, code-specialized |
| 8083 | Qwen 27B (Q5, MTP) | Judge | Thinking mode ON for deep review |
| 8086 | Ornith 35B (Q4) | Scout | AST scans, file surveys, deterministic scouts |

**Fleet status is informational, not gating.** `model-router status` shows what's resident; the router starts/stops/swaps as needed. Don't block on "down" status — request the lane and let the router handle it.

Full routing rules, port assignments, and agent constraints: [docs/fleet-routing-brief.md](docs/fleet-routing-brief.md)

### What tool to use for code work

| Task | Tool | LLM needed? |
|---|---|---|
| Module-level function extraction (refactoring) | `extract_module.py` | No — deterministic |
| Test + lint verification | `local_test_runner.py` | No — wrapper script |
| Codebase survey / seam analysis | `codebase_survey.py` | Yes (builder lane) |
| Code generation (new code, not extraction) | builder-judge-loop.sh | Yes (builder + judge swap) |
| Context compression | `compress_tool_output.py` | Yes (builder lane) |

Scripts live in `~/.hermes/skills/software-development/local-fleet-efficiency/scripts/`.

## Default Workflow: Map, Compress, Route, Verify

For all Dev-Flow codebase work beyond a tiny one-file answer:

1. **Map first** with Agent Proxy `codebase_search` when Dev-Flow is indexed, or Context Map/Graphify when it is not.
2. **Compress large files** before reading them. Use `compress_tool_output.py`, `extract_methods.py`, or `codebase_survey.py`; do not paste large raw files or logs into frontier context.
3. **Check fleet state**: `~/.hermes/scripts/model-router status` and `devflow local-ai snapshot --json`.
4. **Route deliberately.** Qwen3-Coder-Next (:8084) is the builder; Qwen 27B (:8083) is the judge; Ornith 35B (:8086) is the scout. One heavy model at a time.
5. **Verify through compact evidence**: `local_test_runner.py` for test/lint summaries, `devflow architecture audit --json` when Graphify freshness matters, and `fleet_efficiency_report.py` only with real session/response evidence.

This workflow does not make local workers automatic. Local worker starts remain opt-in and must obey the local worker policy below. Mapping, compression, fleet telemetry, and compact test wrappers are the default efficiency path.

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

Local workers are opt-in, not a standing requirement for every non-trivial task.
Use them when the operator explicitly asks for local-worker help, when an active
task selects a local worker, or when a documented diagnostic/verification step
requires one.

When local-worker use is opted in, the fleet is:

- **Qwen3-Coder-Next (:8084)** — builder/coder for code generation, extraction, debugging
- **Qwen 27B (:8083)** — judge for code review, validation, final approval (thinking mode)
- **Ornith 35B (:8086)** — scout for AST scans, file surveys, deterministic codebase inspection

One heavy model runs at a time. The model-router handles starts/stops/swaps
automatically. See [docs/fleet-routing-brief.md](docs/fleet-routing-brief.md)
for full routing rules and constraints.

In Codex sessions, the supported local-worker workflow is the visible subagent
lane: call `multi_agent_v1.spawn_agent` with `agent_type="qwen3_coder_next_coder"`
for builder work or `agent_type="qwen36_27b_mtp_coder"` for judge/review work.
The spawned subagent output surfaced back into the parent Codex session is the
proof that the lane is loaded and usable. Do not treat direct HTTP probes,
Hermes MCP tests, or `/v1/models` checks as equivalent Codex subagent proof.

For Hermes sessions or compact MCP worker packets, use `hermes-qwen-mtp` as the
wrapper around the same Qwen lane: call `qwen_ready(smoke=true)` before
`qwen_run`. That MCP path mirrors the Codex worker packet contract; it is not a
competing default over the visible Codex subagent workflow.

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

Top-level `src/devflow/*.py` files should stay limited to package/CLI entrypoints and explicit bridges into `src/devflow/control_room/`. The legacy `_legacy/` runtime and pure top-level legacy shims have been removed; do not recreate them.

## Working Rules

For ordinary fixes:

1. Read this file.
2. Inspect the smallest relevant implementation or doc files.
3. Make the focused change.
4. Run verification scaled to the risk.
5. Report what changed, what passed, and what remains risky.

Only expand into broader docs when the task actually needs them:

- Product direction: [PRODUCT_NORTH_STAR.md](PRODUCT_NORTH_STAR.md)
- Current control-room contract: [docs/control-room-mvp.md](docs/control-room-mvp.md)
- Architecture cleanup baseline: [docs/architecture/graphify-architecture-baseline.md](docs/architecture/graphify-architecture-baseline.md)
- Verification reuse: [docs/verification-ledger.md](docs/verification-ledger.md)
- DevMode discipline reference: [docs/devmode-contract.md](docs/devmode-contract.md)

Historical handoffs, milestone plans, archived specs, and old workflow notes are reference material. Do not treat them as process authority unless the user explicitly asks for that history.

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

## Stale Context Policy

Stale context is harmful when it claims to be current authority. Clean it up by rewriting, relocating, or marking it historical.

Do not delete future architecture just because it is not active yet. Preserve useful future ideas as roadmap/reference material, but keep them clearly separated from the current product contract.

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
