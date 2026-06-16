# Milestone 26 Operational Baseline / Trust Pass

## Status

complete

## Files Changed

- src/devflow/control_room/promotion.py (kept Git baseline and dirty-check guards only for Git repositories so verified non-git scratch copy-workspace promotion can complete)
- src/devflow/cli.py (matched CLI promotion preflight to the service behavior and kept extra confirmation only for deletion-applying or Git-native promotions)
- tests/test_promote_preview.py (updated promotion approval semantics and added non-git scratch promotion regression coverage)
- tests/test_git_worktree_promotion.py (aligned promotion-preview next-action wording)
- docs/verification-ledger.md (recorded Milestone 26 scratch proof and focused repair evidence)
- docs/control-room-mvp.md, docs/agent-handoff.md, docs/mvp-contract.md (marked Milestone 26 complete and aligned the next safe product direction)
- docs/handoffs/2026-06-16-milestone-26-operational-baseline-trust-pass.md (this closure handoff)

## Verification

- `PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_promote_preview.py tests/test_git_worktree_promotion.py -q`: pass, `38 passed in 23.99s`
- `PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_promote_preview.py tests/test_git_worktree_promotion.py tests/test_operating_layer.py::test_operating_layer_server_runs_approved_task_promotion -q`: pass, `39 passed in 25.01s`
- Milestone 26 scratch proof with module entrypoint: pass; scratch task `task-0001` reached `promoted`, `result.txt` stayed in `.devflow/workspaces/task-0001/` before promotion and appeared in the scratch root after promotion
- `git diff --check`: pass
- `rg -n "Milestone 26|Operational Baseline|Trust Pass|current slice|next milestone" docs README.md PRODUCT_NORTH_STAR.md`: pass; remaining hits describe Milestone 26 as complete or historical context

## Risks

- Full pytest was not rerun; the verification ledger reserves it for release gates, broad shared behavior changes, or explicit request.
- Default copy-workspace promotion no longer asks for a second prompt after `promote-preview`; deletion-applying and Git-native promotions still prompt because they can remove files or merge refs.

## Next Safe Action

- Choose the next milestone explicitly; if it moves toward non-shell runtime work, start with registry architecture/contract alignment and registry list/show/packet surfaces before implementing any provider adapter.
