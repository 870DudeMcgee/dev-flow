# VS Code-Only Mac Mini M1 Onboarding Plan

Date: 2026-05-26
Status: READY FOR EXECUTION
Owner: Human + VS Code/Copilot orchestrator
Scope: Mac mini M1 (16 GB), VS Code only lane

## Goal

Bring this Mac mini into a known-good `devflow` operating state for VS Code/Copilot orchestration with local model workers, while preserving the existing multi-orchestrator contract.

This plan assumes:
- Antigravity will be wired later and is out of scope for this execution.
- A local coding model download is in progress and may complete during execution.

## Non-Goals

- No changes to MVP `devflow run` behavior.
- No provider routing integration in core runtime.
- No permanent role lock for any IDE.

## Success Criteria

1. VS Code can run all `devflow` CLI flows from this repo.
2. Local worker preflight passes on this machine.
3. Unit tests pass from the selected Python environment.
4. A VS Code-only smoke audit pass is recorded and reproducible.
5. Evidence is documented in one machine setup log.

## Phase Plan

## Phase 0: Baseline Snapshot (10-15 min)

Actions:
1. Capture machine metadata:
   - macOS version
   - CPU/RAM summary
   - Xcode CLI tools status
2. Capture repo metadata:
   - current branch
   - git worktree cleanliness
   - latest commit hash
3. Record current VS Code version and installed extension IDs relevant to Python/Copilot.

Deliverable:
- completed setup log section: Baseline Snapshot

Exit Gate:
- baseline commands executed and outputs recorded

## Phase 1: Python + Repo Runtime Readiness (15-25 min)

Actions:
1. Ensure Python 3.12+ is available.
2. Create/refresh `.venv` in repo root.
3. Install project editable package: `pip install -e .`.
4. Execute unit tests from `.venv`.
5. Verify CLI entrypoint starts: `python -m devflow --help` and/or `.venv/bin/devflow --help`.

Deliverable:
- completed setup log section: Python Runtime Readiness

Exit Gate:
- tests pass and CLI help works

## Phase 2: VS Code Orchestrator Readiness (10-20 min)

Actions:
1. Confirm VS Code terminal opens in repo root.
2. Confirm Copilot chat and coding mode are functional in workspace.
3. Validate key runbook paths are visible in explorer:
   - `docs/workflows/local-worker-health-check-runbook.md`
   - `docs/workflows/hello-peer-orchestrator-vscode.md`
   - `docs/workflows/vscode-smoke-audit-handoff.md`
4. Confirm no conflicting workspace state:
   - no pending task claim collisions
   - worktree clean before any `devflow run`

Deliverable:
- completed setup log section: VS Code Readiness

Exit Gate:
- VS Code-only lane can execute commands and access required docs

## Phase 3: Local Worker Connectivity (10-20 min, model-download dependent)

Actions:
1. Run doctor and endpoint checks:
   - `bash scripts/local_models_doctor.sh`
   - `curl /api/version`
   - `curl /api/tags`
2. Confirm preferred coding model visibility in tags output.
3. Run generation probe:
   - `python3 scripts/local_agent_runner.py "Return only: LOCAL_WORKER_OK"`
4. If missing model, complete pull/download and rerun probes.

Deliverable:
- completed setup log section: Local Worker Preflight

Exit Gate:
- probe returns expected token and exit status is zero

## Phase 4: VS Code Smoke Audit Pass (15-30 min)

Actions:
1. Execute the audit workflow in:
   - `docs/workflows/vscode-smoke-audit-handoff.md`
2. Re-run verification command expected by smoke audit.
3. Record PASS/FAIL findings and notes.
4. If FAIL, attach command output and remediation proposal.

Deliverable:
- completed setup log section: VS Code Smoke Audit

Exit Gate:
- explicit PASS/FAIL with evidence and next action

## Phase 5: Operational Hardening (Optional, 15 min)

Actions:
1. Add machine-specific caveats encountered on this Mac mini.
2. Update runbook commands if path or environment details differ.
3. Record repeatable recovery steps for any failures observed.

Deliverable:
- completed setup log section: Hardening Notes

Exit Gate:
- known issues and recovery paths documented

## Risk Register

1. Model download incompletion delays preflight.
   - Mitigation: execute Phases 0-2 first, block only Phase 3 onward.
2. Python linkage or gatekeeper issues on this machine.
   - Mitigation: apply repair sequence documented in `README.md` and `docs/agent-handoff.md`.
3. Dirty worktree blocks `devflow run` preview/apply.
   - Mitigation: commit or stash before run, following clean-worktree gate.
4. Orchestrator ownership collisions on active tasks.
   - Mitigation: use claim metadata and avoid touching claimed scope.

## Documentation Outputs (Required)

1. Machine setup log file in docs/workflows:
   - `docs/workflows/vscode-only-machine-setup-log.md`
2. Any newly discovered machine caveats added to:
   - `docs/agent-handoff.md` (if globally relevant)
   - `README.md` troubleshooting (if user-impacting and repeatable)
3. Audit result note recorded in the setup log.

## Execution Order While Model Downloads

Recommended now:
1. complete Phase 0
2. complete Phase 1
3. complete Phase 2
4. wait for model availability
5. complete Phases 3-4
6. run Phase 5 only if needed

## Definition of Done

This machine is considered onboarded when all are true:
1. `.venv` tests pass
2. `devflow` CLI works in VS Code terminal
3. local worker probe returns `LOCAL_WORKER_OK`
4. smoke audit has recorded PASS or an explicit blocked state with remediation
5. setup log is complete and committed
