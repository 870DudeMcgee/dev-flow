# Roadmap

## MVP (Current)

- Canonical .devflow tree initialization
- peer orchestrator coordination model (Codex, VS Code/Cline, Antigravity)
- per-task ownership and touched-file declarations
- task claim/release/status commands
- task new command and canonical examples
- peer orchestrator templates in .devflow/orchestrators
- Task schema parsing (sections 1..10)
- Unified diff detection/apply flow
- Protected-file gating
- Checkpoint branch creation
- Verification command selection (config -> auto-detect)
- Failure classification and retry budget handling
- Rollback behavior
- Per-task report generation
- Status command

## Stabilization Queue

- test runner path cleanup (`PYTHONPATH=src` should not be required long-term)

Completed:
- package metadata and CLI entrypoint
- task ownership metadata parsing and reporting
- shared-folder dirty-state guardrails
- run approval policy: preview by default, `--yes` applies
- glob-aware allowed-file checks
- config default alignment
- checkpoint-based rollback semantics
- best-effort plan status mirroring

## Next Milestone

- devflow plan command
- richer goal/plan/task lifecycle commands
- stronger peer orchestrator federation automation
- shared local model worker pool policies
- richer risk scoring and approval policy
- failure route targets to specialized agents
- context/index automation
- richer report artifacts and dashboards
