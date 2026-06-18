# Dev-Flow Agent Guide

Dev-Flow is a local-first control room for AI coding workers. It should automate as much routine work as it safely can while keeping task state, worker identity, evidence, verification, and promotion visible to the human operator.

This file is the first-read instruction surface for agents. Use it to start useful work quickly. Do not turn every task into a repository archaeology pass.

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

The canonical UI title is `Dev-Flow Operating Layer`. The first viewport should expose the real control-room workbench: `Brainstorm`, `Pipeline`, `Worker lanes`, `Review queue`, and `Evidence stream`. The old static files under `public/` are not the active product UI and must not be used for validation.

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

## Where To Work

Active control-room implementation belongs in:

```text
src/devflow/control_room/
tests/
docs/
```

Top-level `src/devflow/*.py` files are mostly CLI entrypoints or compatibility bridges. Touch them only when the active control-room API requires it. Do not add new product behavior under `src/devflow/_legacy/`.

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
- Verification reuse: [docs/verification-ledger.md](docs/verification-ledger.md)
- DevMode discipline reference: [docs/devmode-contract.md](docs/devmode-contract.md)

Historical handoffs, milestone plans, archived specs, and old workflow notes are reference material. Do not treat them as process authority unless the user explicitly asks for that history.

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
