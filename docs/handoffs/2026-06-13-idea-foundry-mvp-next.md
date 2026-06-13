# Idea Foundry MVP Handoff

## Status

complete

## Files Changed

- src/devflow/control_room/paths.py (added the project-local ideas directory helper)
- src/devflow/control_room/idea_foundry.py (Idea Foundry metadata, evidence files, events, state transitions, and renderers)
- src/devflow/cli.py (added `devflow idea capture/list/show/classify/promote/archive`)
- src/devflow/control_room/supervisor_surface.py (classified idea list/show as read-only and idea evidence writes as approval-required)
- tests/test_idea_foundry.py (service and CLI coverage)
- tests/test_supervisor_operating_surface.py (idea supervisor policy coverage)
- README.md (current Idea Foundry command and artifact contract)
- docs/control-room-mvp.md (current behavior alignment)
- docs/mvp-contract.md (stable command and evidence contract alignment)
- docs/roadmap.md (Milestone 12 status and next priority)
- docs/architecture/patch-evidence-ladder.md (current local intake wording)
- docs/superpowers/specs/2026-06-13-idea-foundry-mvp-design.md (implemented status)
- docs/superpowers/plans/2026-06-13-idea-foundry-mvp.md (historical status)
- docs/handoffs/2026-06-13-idea-foundry-mvp-next.md (this current handoff)

## Verification

- `PYTHONPATH=src:. <repo-root>/.venv/bin/python -m pytest tests/test_idea_foundry.py tests/test_supervisor_operating_surface.py -v`: pass, 23 passed
- `PYTHONPATH=src:. <repo-root>/.venv/bin/devflow idea --help`: pass, lists capture/list/show/classify/promote/archive
- `PYTHONPATH=src:. <repo-root>/.venv/bin/devflow idea list`: pass, `No ideas found.`
- `git diff --check`: pass, no output
- stale-context `rg`: pass, no future-only matches in active docs
- `PYTHONPATH=src:. <repo-root>/.venv/bin/devflow task verify task-0022 --shell 'PYTHONPATH=src:. <repo-root>/.venv/bin/python -m pytest tests/test_idea_foundry.py tests/test_supervisor_operating_surface.py -v' --timeout-seconds 120`: pass, verification log reports 23 passed

## Risks

- `idea promote` records decision evidence only; it still creates no goals or tasks.
- The worker branch was fast-forwarded to local `main` checkpoint `4bba74b` before implementation because `task create --git-worktree` started from `origin/main`.
- The branch is local until Josh approves promotion and push.

## Next Safe Action

- Run `devflow task promote-preview task-0022` from the main checkout and review readiness before any promotion or push.
