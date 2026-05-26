# Roadmap

## MVP (Current)

- Canonical .devflow tree initialization
- peer orchestrator coordination model (Codex, VS Code/Copilot, Antigravity)
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
- Rich report audit trail
- Status command
- Future model routing documented as post-MVP only

## Stabilization Queue

- no open MVP stabilization items

Completed:
- package metadata and CLI entrypoint
- editable install verified with Homebrew Python 3.12
- local macOS/Homebrew startup hang repaired by restarting `syspolicyd`
- local Python `pyexpat` linkage repaired for Homebrew Python 3.12 and 3.14
- local `.venv` editable-import path repaired by clearing macOS hidden flags
- task ownership metadata parsing and reporting
- shared-folder dirty-state guardrails
- run approval policy: preview by default, `--yes` applies
- glob-aware allowed-file checks
- config default alignment
- checkpoint-based rollback semantics
- best-effort plan status mirroring
- local worker health-check runbook authored
- smoke integration proving goal/plan/task pack authored
- smoke integration proving run executed end-to-end (claim, preview, apply, verify, report)
- proving edge case documented: trailing blank-context diff hunks can be corrupted by extraction whitespace trimming
- proving edge case documented: same-second preview/apply checkpoint branch collision can require immediate retry

## Next Milestone

- local AI dev team integration execution (Codex, VS Code/Copilot, Antigravity + local workers)
- thin local dispatcher contract and health-check runbook
- end-to-end integration proving project (`smoke-multi-agent-todo-cli`)
- VS Code/Copilot-only audit handoff pass for smoke proving artifacts
- devflow plan command
- richer goal/plan/task lifecycle commands
- stronger peer orchestrator federation automation
- shared local model worker pool policies
- richer risk scoring and approval policy
- failure route targets to specialized agents
- context/index automation
- richer report artifacts and dashboards
