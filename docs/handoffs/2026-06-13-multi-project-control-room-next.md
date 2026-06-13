# Multi-Project Control Room Next Handoff

## Status

needs-review

## Files Changed

- `docs/roadmap.md` (Milestone 15 set as the next planned multi-project control-room hardening slice)
- `docs/control-room-mvp.md` and `docs/mvp-contract.md` (current-priority callouts point from Milestone 14A closure to multi-project hardening)
- `docs/handoffs/2026-06-13-multi-project-control-room-next.md` (this handoff)

## Verification

- `DEVFLOW_HOME=/Users/josh/.devflow PYTHONPATH=src:. .venv/bin/devflow freshness run --all-projects --max-iterations 1 --json`: human-decision evidence, checked 5 registered projects and stopped on stale registry entry `approval-review-demo-project`
- `PYTHONPATH=src:. .venv/bin/devflow dogfood run --suite production-readiness`: pass, `score: 110/110`, `silver_met: yes`
- `PYTHONPATH=src:. .venv/bin/python -m pytest`: pass, `941 passed, 6 skipped`

## Risks

- The real global registry at `/Users/josh/.devflow/registry/projects.json` contains stale `/private/tmp/...` project paths from earlier UI/dogfood work.
- This shell has `DEVFLOW_HOME=/Users/josh/Desktop/Dev-Flow`; all-projects commands use an empty repo-local home unless the next agent deliberately points at `/Users/josh/.devflow`.
- Multi-project work must preserve project-local `.devflow/` authority and must not introduce provider routing, remote publication, PR automation, or database state.

## Next Safe Action

- Start the Milestone 15 spec by running `DEVFLOW_HOME=/Users/josh/.devflow PYTHONPATH=src:. .venv/bin/devflow project doctor approval-review-demo-project` and deciding the registry archive/repair policy for stale project paths.
