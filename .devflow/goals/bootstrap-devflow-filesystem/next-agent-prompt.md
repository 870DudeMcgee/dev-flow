# Next Agent Prompt: Bootstrap Filesystem Cleanup Branch

You are continuing Dev-Flow in `/Users/josh/Desktop/Dev-Flow`.

## Current Branch

Branch: `devflow/task-022-clean`

This branch was rebuilt from current `origin/main` after the older `devflow/task-022-20260527014930` branch failed a merge check against `main`.

## Scope

Keep this branch focused on:

1. Seeded `.devflow/` project, goal, context, layer, worker, model, lock, report, archive, and task orientation files.
2. `devflow init` repair support for the seed structure.
3. `devflow doctor` seed contract validation.
4. Evidence-gated promotion readiness using canonical task state plus current passed `verification.json`.
5. Derived `merge-readiness.json` and `summary.json` alignment with the same readiness rule.

Do not add dashboards, AI adapters, model routing, databases, PR automation, auto-merge, worktree orchestration, or legacy workflow ceremony.

## Merge Cleanup Notes

- The old branch conflicted with `origin/main` in `README.md` and `src/devflow/control_room/service.py`.
- This clean branch keeps `origin/main`'s README and current control-room module layout.
- Readiness helpers live in `src/devflow/control_room/readiness.py` so promotion, service, and persistence can share the same evidence-gated decision without circular imports.
- The old long manual integration repair plan was intentionally left out of this cleanup branch.

## Verification To Run

```bash
git diff --check
.venv/bin/python -m pytest tests/test_control_room_shell.py tests/test_promote_preview.py tests/test_devflow_init_structure.py -q
.venv/bin/python -m pytest -q
git merge-tree origin/main HEAD
```

## Next Safe Action

Push this clean branch and use it as the merge target instead of the older divergent branch.
