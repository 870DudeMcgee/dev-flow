# DevFlow Agent Guide

DevFlow is the V2 local product-building loop. It takes a rough idea through
brainstorm, specification, planning, review, bounded execution, verification,
and the next explicit human decision.

## Authority and Scope

1. Read [docs/DEVFLOW_SOURCE_OF_TRUTH.md](docs/DEVFLOW_SOURCE_OF_TRUTH.md) before changing product direction, workflow, or the status board.
2. The only active runtime surfaces are:
   - `src/devflow/loop/` — deterministic V2 loop, persistence, scout, and model-slot contracts.
   - `src/devflow/control_room/` — status board and brainstorm chat surface.
   - `src/devflow/control_room/chat.py` — brainstorm chat backend (model listing, session management, message dispatch).
   - `src/devflow/cli.py` — V2-only command entrypoint.
3. The browser is the unified brainstorm and status surface. It hosts a live status board on the left and a brainstorm chat panel on the right. Hermes remains the orchestration harness and bounded worker runtime; it is no longer the only brainstorm surface.
4. Historical code and documents were removed from this checkout. Recover them only when a human explicitly requests archival recovery; do not recreate compatibility shims or older UI flows.

Before any subagent planning, worker routing, dispatch, retry, fallback, or
delegated integration, read the machine-wide
[`SUBAGENT_RULEBOOK.md`](SUBAGENT_RULEBOOK.md). Its scope is general Codex
building and usage. The repository-specific rules in this file and `docs/`
supplement it only for work in this repository.

## Current Commands

```bash
PYTHONPATH=src .venv/bin/python -m devflow.cli status serve
PYTHONPATH=src .venv/bin/python -m devflow.cli loop spine-fixture --json
```

`loop spine-fixture` is deterministic regression evidence. It makes no model
calls and does not replace model-backed execution work.

## Product Boundaries

- **User:** intent, taste, priority, acceptance, and final decisions.
- **Obsidian:** broad knowledge and long-lived notes.
- **DevFlow:** the active product-building loop and its local evidence.
- **Git/filesystem:** source of record for code and artifacts.
- **Hermes:** messaging, tools, and bounded worker orchestration.
- **Local models:** replaceable bounded labor, never silent authority.

DevFlow is model-agnostic and machine-agnostic. Do not present one profile or
one machine's local fleet as the architecture. Resolve the host registry,
active profile, live endpoint identity, and qualification evidence separately;
then recommend the closest proven mode for operator approval. The exact contract
and current gaps are in `docs/DEVFLOW_SOURCE_OF_TRUTH.md`.

Do not add broad dashboards, hidden automation, a model zoo, or speculative
architecture back into the active surface.

## Working Rules

1. Orient from current source and tests; do not trust old handoffs or generated artifacts.
2. Keep work bounded. Read the exact loop/control-room files that own the behavior before editing.
3. Preserve the status board's refresh invariants: user selections, expanded state, artifact view, and pane scroll positions survive refresh.
4. Do not start local model servers blindly. Check live fleet state through the approved model-router workflow first.
5. Do not push, publish, open a PR, or promote work without explicit human approval.
6. Keep active documentation sparse. Update the source of truth, this guide, or README only when the current behavior changes.
7. When the human asks for delegated work, give sub-agents bounded reading,
   evidence, or implementation slices and keep the primary agent responsible
   for integration and proof. Prefer the cheapest capable worker when the
   orchestration surface exposes model or cost selection; do not imply that a
   model was selected when the surface does not expose that control.
8. During the M1 local-role audition process, follow
   [docs/M1_LOCAL_ROLE_AUDITION_PLAN.md](docs/M1_LOCAL_ROLE_AUDITION_PLAN.md):
   use Hermes `tencent/hy3:free` workers by default and record actual route,
   tools, failures, and fallback. Tool-required packets use native
   `delegate_task` with the smallest exact toolsets. Fully supplied text-only
   packets may use the plan's durable-receipt adapter and exact quoted-heredoc
   `--stdin` command; the flag alone does not feed the packet. If no terminal
   receipt exists, retry the same packet and anchors on the unchanged HY3-first
   route instead of manually skipping to a fallback. Use the initial free
   attempt plus up to three corrected free retries before native Luna. Do not
   check Luna availability or stop free work before that budget is exhausted.
   Keep the configured fallback free unless the human explicitly authorizes a
   paid route. GPT-5.6 Sol remains responsible for integration and proof.

## Verification

- Documentation changes: `git diff --check` plus a targeted stale-context scan.
- CLI/loop changes: run the focused V2 loop and CLI tests.
- Status-board changes: run focused control-room tests; use the render harness or browser only when the changed behavior requires it.
- Before declaring completion: prove imports, command help, and relevant tests from real command output.

## Git Safety

There may be unrelated user work in the checkout. Never revert changes you did
not create. Use a scoped branch for broad refactors. Do not push unless the
human explicitly asks.
