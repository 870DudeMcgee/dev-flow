# Milestone 24 Intent-To-Goal/Task Scaffold Next Handoff

## Status

needs-review

## Files Changed

- `docs/superpowers/specs/2026-06-15-milestone-24-intent-to-goal-task-scaffold-design.md` (Milestone 24 design spec)
- `docs/superpowers/plans/2026-06-15-milestone-24-intent-to-goal-task-scaffold.md` (step-by-step implementation plan)
- `docs/control-room-mvp.md` (current priority updated to the approved Milestone 24 slice)
- `docs/mvp-contract.md` (current priority updated to the approved Milestone 24 slice)
- `docs/roadmap.md` (Milestone 24 section added)
- `docs/agent-handoff.md` (current direction and next safe action updated)
- `docs/handoffs/2026-06-15-milestone-24-intent-to-goal-task-scaffold-next.md` (this handoff)

## Verification

- `PYTHONPATH=src:. .venv/bin/devflow git status`: pass before edits, clean `main`, synced with `origin/main`
- `PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_devmode_contract.py tests/test_workflow_orchestration_docs.py tests/test_project_scope_docs.py tests/test_release_readiness.py -q`: pass, 24 passed
- targeted placeholder scan across the Milestone 24 spec, plan, and handoff: pass, no placeholder matches
- targeted stale-priority scan across active docs and the Milestone 24 planning docs: pass, no stale active-priority or false implementation matches

## Risks

- Existing Telegram bridge code still contains older mutation-oriented behavior. The Milestone 24 implementation must bring it behind approval-gated scaffold evidence before treating Telegram/DM intent intake as safe.
- Milestone 24 must not add provider execution, autonomous routing, worker auto-run, verification auto-run, promotion, commits, pushes, PRs, databases, hidden memory, RAG, embeddings, or training.

## Next Safe Action

- Create the Milestone 24 implementation task and start Task 1 from the plan: characterize the current intent-to-goal behavior with failing focused tests.
