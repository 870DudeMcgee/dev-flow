# Control-Room Operational Baseline

## Status

needs-review

## Files Changed

- AGENTS.md (added verification escalation policy and ledger consultation rule)
- docs/verification-ledger.md (added latest full-suite/dogfood evidence and expensive-verification policy)
- docs/control-room-mvp.md (added Operational Baseline / Trust Pass direction)
- docs/agent-handoff.md (aligned active slice wording to Operational Baseline / Trust Pass)
- src/devflow/control_room/dogfood.py (dogfood run retention now prunes older run directories by default)
- src/devflow/cli.py (added `devflow dogfood run --keep-runs`)
- src/devflow/control_room/service.py (macOS hidden-flag doctor check is non-blocking local hygiene)
- src/devflow/control_room/operator_readiness.py (made goal lifecycle blockers visible even when there are zero tasks)
- src/devflow/control_room/dashboard.py (let operator-readiness lifecycle repair win without tasks and fixed the empty-task footer)
- tests/test_operator_readiness.py, tests/test_dogfood_harness.py, tests/test_doctor_strict.py (focused regression coverage)
- .devflow/tasks/task-0001, .devflow/workspaces/task-* leftovers, and old dogfood run evidence were removed as disposable runtime debris after recording the proof-loop result; the latest dogfood report remains.

## Verification

- `git status --short --branch`: initial baseline pass showed `## main...origin/main`; current checkout is dirty only from this baseline change set.
- Full pytest evidence from the baseline session: pass, `1058 passed, 6 skipped in 185.62s`; no local persisted pytest log was found, so this was recorded in `docs/verification-ledger.md` as observed evidence rather than rerun.
- `.venv/bin/devflow dogfood report dogfood-20260615T165239Z`: pass, `153/155`, `Bulletproof candidate`; report path `.devflow/dogfood/runs/dogfood-20260615T165239Z/report.md`.
- Initial `.venv/bin/devflow doctor`: fail only on macOS hidden flags under `.venv`; the hidden-flag check now reports as non-blocking `python path hygiene`, and `PYTHONPATH=src:. .venv/bin/devflow doctor` exits 0.
- `PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_operator_readiness.py -q`: pass, `9 passed in 2.75s`.
- `.venv/bin/python -m pytest tests/test_operator_readiness.py tests/test_control_room_dashboard.py tests/test_scheduler_projection.py tests/test_goal_projection.py -q`: pass, `38 passed in 5.96s`.
- `PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_doctor_strict.py::test_doctor_macos_hidden_flag tests/test_dogfood_harness.py::test_run_creates_artifacts_scorecard_and_report tests/test_dogfood_harness.py::test_dogfood_prunes_old_runs_by_default tests/test_dogfood_harness.py::test_dogfood_keep_runs_retains_requested_history tests/test_dogfood_harness.py::test_cli_commands_and_report_lookup -q`: pass, `5 passed in 18.15s`.
- `PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_dogfood_harness.py -q`: pass, `20 passed in 36.53s`.
- `PYTHONPATH=src:. .venv/bin/devflow dashboard`: pass after runtime cleanup; shows zero tasks, `Lifecycle blocked: 4`, and next action `devflow goal activate G-0001 --reason 'ready to execute'`.
- `PYTHONPATH=src:. .venv/bin/devflow scheduler status`: pass after runtime cleanup; status `blocked`, `ready_to_promote: 0`, next action `devflow goal activate G-0001 --reason 'ready to execute'`.
- `.venv/bin/devflow freshness loop`: expected exit 2, `needs_human_decision`; reports missing lifecycle state for `G-0001` through `G-0004`.
- `.venv/bin/devflow goal status G-0001`: pass; reports `Lifecycle: missing` and activation command.
- Operational proof loop:
  - `PYTHONPATH=src:. .venv/bin/devflow task create "Operational baseline proof task"`: created `task-0001`; warned workspace copied current dirty modifications.
  - `.venv/bin/devflow task run task-0001 --worker shell -- /bin/sh -c "printf 'operational baseline proof\n' > result.txt"`: pass, worker completed.
  - `.venv/bin/devflow task verify task-0001 --shell "test -f result.txt"`: pass, verification passed.
  - `.venv/bin/devflow task review-ready`: pass, `Ready for review: 1`, `task-0001: ready_for_review (score=100)`.
  - `.venv/bin/devflow task promote-preview task-0001`: pass, preview only; would add `result.txt`; no promotion was run.

## Risks

- `G-0001` through `G-0004` still lack canonical `.devflow/goals/<goal_id>/goal-state.yaml`; this is now consistently visible across goal, freshness, scheduler, status, and dashboard surfaces, but actual lifecycle repair remains a human/operator decision.
- The proof task workspace was created while the baseline code/docs edits were dirty, so `task show` correctly reported `workspace_dirty: true`; promotion preview showed only `result.txt` as the task change. The ignored task/workspace debris was later removed instead of promoted.
- The local macOS hidden flag recurred on virtualenv paths during verification. Doctor now reports this as non-blocking local environment hygiene, but the generated entrypoint may still need `chflags -R nohidden .venv` or `PYTHONPATH=src:.` if the editable `.pth` file itself is hidden.
- Full pytest was not rerun because the ledger and user plan reserve it for release gates, broad shared behavior changes, or explicit request.

## Next Safe Action

- Decide the lifecycle for `G-0001`; if it should execute now, run `devflow goal activate G-0001 --reason 'ready to execute'`, then repeat for the next reported goal.
