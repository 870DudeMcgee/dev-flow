# Goal: 002 Smoke Multi-Agent Integration

Date: 2026-05-26
Status: READY

## Outcome

Prove peer-orchestrator + local-worker collaboration in a clean temporary repository by completing one task end-to-end using `devflow` claim, preview, apply, verification, report, and handoff.

## Success Criteria

- local worker preflight passes
- task is claimed before mutation
- preview run writes `PREVIEWED` and report
- apply run with `--yes` writes `COMPLETED` and report
- peer orchestrator can audit using task + report only

## Constraints

- unified diff only
- clean worktree required before `devflow run` mutation
- no protected-path touches
- no in-run model/provider calls inside `devflow run`
