# Roadmap

## Strategic Direction

- devflow should become the deterministic control plane for bounded AI software engineering across Codex, Claude Code, Copilot, Cline, Antigravity, OpenCode, local Ollama models, humans, and future tools.
- Current strategic source of truth: `docs/superpowers/specs/2026-05-27-devflow-agentic-control-plane-spec.md`.
- Current implementation source of truth: `docs/plans/2026-05-27-devflow-agentic-control-plane-implementation-plan.md`.
- Core design rule: local and cloud workers produce schema-validated artifacts; only devflow may preview, apply, verify, rollback, and report repository mutations.
- VS Code/Copilot users can invoke the workflow through the single workspace `/devflow` skill, backed by `.github/skills/devflow/SKILL.md` and mode references under `.github/skills/devflow/references/`.
- `examples/devflow-hello/` provides a tiny dependency-free project for proving task claim, implementation, verification, and reporting loops.

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
- Artifact kernel with metadata/body storage, hashing, lineage fields, list command, and inspect command
- Context pack compiler with deterministic repo maps and context pack artifacts
- Review-only worker adapter with local profile loading, Ollama invocation, review result validation, and review artifacts
- Diff-only implementer artifacts with deterministic diff validation and guard scanning
- Failure classification and bounded repair worker command surface
- TDD state transitions and structured verification recipes
- Task DAG and impact analysis commands
- Trace and eval command surface for harness evidence
- Worktree-native parallelism with explicit create/status/remove commands and metadata
- Architectural memory invalidation with memory list/add/inspect commands and context-pack stale-memory exclusion
- VS Code/Copilot workspace skill discovery through `/devflow`
- Minimal hello-world workflow smoke project under `examples/devflow-hello/`
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
- agentic control plane Phase 1 artifact kernel implemented with `devflow artifact list` and `devflow artifact inspect`
- artifact schema packaged under `src/devflow/schemas/artifact.schema.json`
- agentic control plane Phase 2 context pack compiler implemented with `devflow context refresh/build/inspect/list`
- repo maps generated as `.devflow/context/repo-map.short.md`, `.devflow/context/repo-map.symbols.json`, and `.devflow/context/repo-map.deps.json`
- agentic control plane Phase 3 review-only worker adapter implemented with `devflow agent review`
- review output is schema-validated and stored as non-mutating `review.json` artifacts
- agentic control plane Phase 4 diff-only implementer stores schema-validated diff artifacts and supports `devflow guard scan-diff`
- agentic control plane Phase 5 repair loop stores failure and repair artifacts without direct repo mutation
- agentic control plane Phase 6 TDD transitions and structured verification recipes are implemented
- agentic control plane Phase 7 task DAG and impact analysis commands are implemented
- agentic control plane Phase 8 traces and deterministic evals are implemented
- agentic control plane Phase 9 worktree-native parallelism is implemented with `devflow worktree create/status/remove`
- agentic control plane Phase 10 memory invalidation engine is implemented with `.devflow/memory/` records, post-apply staling, and context-pack filtering
- CLI decomposition objective is completed: `src/devflow/cli.py` is now parser/dispatch oriented with command logic extracted into focused modules (`task_commands.py`, `runner.py`, `worktree_commands.py`, `trace_eval_commands.py`, `resource_commands.py`, `admin_commands.py`, `lifecycle_commands.py`)

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
