## Status

needs-review

## Files Changed

- `src/devflow/control_room/question_resume.py` (question projection plus answer/resolve evidence records)
- `src/devflow/cli.py` (new `devflow question` command group)
- `src/devflow/control_room/scheduler_projection.py` (question-aware blocker and resume projection)
- `src/devflow/control_room/supervisor_surface.py` (question command classification and packet summary)
- `src/devflow/control_room/operating_layer.py` (question ids and answer commands in snapshot/inbox)
- `src/devflow/control_room/dogfood.py` (question blocker resume loop dogfood case)
- `tests/test_question_resume.py`, scheduler, supervisor, operating-layer, and dogfood tests
- active docs and Milestone 22 planning artifacts (current contract plus historical status)

## Verification

- `PYTHONPATH=src:. /Users/josh/Desktop/Dev-Flow/.venv/bin/python -m pytest tests/test_question_resume.py tests/test_scheduler_projection.py tests/test_supervisor_operating_surface.py tests/test_operating_layer.py tests/test_dogfood_harness.py -q`: pass, `78 passed in 78.08s (0:01:18)`
- `PYTHONPATH=src:. /Users/josh/Desktop/Dev-Flow/.venv/bin/devflow dogfood run --suite production-readiness`: pass, `score: 136/138`, `threshold: Bulletproof candidate`, `silver_met: yes`; warning: `parallelism-decision-docs-test-split` was conservatively blocked by current repo guardrails while role/context checks still ran
- `rg -n "question answering.*future-only|question resume.*later|Milestone 22.*planned next|auto-resume is active|provider-backed question execution|browser question answer mutation" docs README.md AGENTS.md -S`: pass, hits only historical plan/spec verification text
- `PATH=/Users/josh/Desktop/Dev-Flow/.venv/bin:$PATH ./scripts/release-check.sh`: pending until branch commit makes the worktree clean

## Risks

- None identified after focused verification. Full release-check is pending a clean committed branch.

## Next Safe Action

- `PYTHONPATH=src:. /Users/josh/Desktop/Dev-Flow/.venv/bin/devflow task finalize task-0043 --commit`
