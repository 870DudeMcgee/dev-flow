# 2026-06-18 Task Workbench Projection Handoff

## Status

ready-for-implementation

## Outcome

- Documented the operating-layer UI deepening backlog.
- Added `CONTEXT.md` domain vocabulary for architecture reviews.
- Wrote the Task workbench projection design spec.
- Wrote a handoff-ready implementation plan for another agent.
- Linked the backlog from the active control-room contract.
- No production code was changed by this documentation pass.

## Files Changed

- `CONTEXT.md` - domain vocabulary for current architecture reviews.
- `docs/architecture/operating-layer-ui-deepening-backlog.md` - ranked backlog of UI architecture fixes.
- `docs/control-room-mvp.md` - added a discoverability link to the backlog.
- `docs/superpowers/specs/2026-06-18-task-workbench-projection-design.md` - design for candidate 1.
- `docs/superpowers/plans/2026-06-18-task-workbench-projection.md` - implementation plan for candidate 1.
- `docs/handoffs/2026-06-18-task-workbench-projection-next.md` - this handoff.

## Verification

- `git diff --check`: passed with no output.
- `grep -n '[[:blank:]]$' CONTEXT.md docs/architecture/operating-layer-ui-deepening-backlog.md docs/superpowers/specs/2026-06-18-task-workbench-projection-design.md docs/superpowers/plans/2026-06-18-task-workbench-projection.md docs/handoffs/2026-06-18-task-workbench-projection-next.md`: passed with no output.
- `rg -n "Task workbench|task_workbench|operating-layer-ui-deepening-backlog|Hyperplane|public/|future provider|Status: active things to fix" CONTEXT.md docs/control-room-mvp.md docs/architecture/operating-layer-ui-deepening-backlog.md docs/superpowers/specs/2026-06-18-task-workbench-projection-design.md docs/superpowers/plans/2026-06-18-task-workbench-projection.md docs/handoffs/2026-06-18-task-workbench-projection-next.md`: passed; matches were intentional backlog/spec/plan references and existing active warnings.

## Risks

- The worktree already contained unrelated code/UI changes before this documentation pass. Do not revert them.
- The plan is intentionally architecture-first. The implementation agent should still inspect the current code before editing.
- Candidate 2, browser action/capability deepening, is adjacent but not part of this first implementation handoff.

## Recommended Next Steps

- Hand `docs/superpowers/plans/2026-06-18-task-workbench-projection.md` to an implementation agent.
- Start with `tests/test_task_workbench_projection.py` so the new Module has a focused Interface test before refactoring `operating_layer.py`.
- Keep browser behavior stable unless the implementation exposes a concrete usability bug.

## Next Safe Action

Ask the next agent to implement `docs/superpowers/plans/2026-06-18-task-workbench-projection.md`, starting with the focused failing tests for `build_task_workbench()`.
