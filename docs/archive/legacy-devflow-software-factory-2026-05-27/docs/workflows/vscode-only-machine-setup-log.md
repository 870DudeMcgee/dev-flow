# VS Code-Only Machine Setup Log

Date: 2026-05-26
Machine: Mac mini M1 16 GB
Status: PARTIALLY COMPLETE
Owner: Human + VS Code/Copilot orchestrator

Use this log with:
- `docs/plans/2026-05-26-vscode-only-mac-mini-onboarding-plan.md`
- `docs/workflows/local-worker-health-check-runbook.md`
- `docs/workflows/vscode-smoke-audit-handoff.md`

## 1) Baseline Snapshot

Commands run:
- [x] `sw_vers`
- [x] `uname -a`
- [x] `sysctl -n machdep.cpu.brand_string`
- [x] `system_profiler SPHardwareDataType | head -n 20`
- [x] `xcode-select -p`
- [x] `git rev-parse --abbrev-ref HEAD`
- [x] `git rev-parse HEAD`
- [x] `git status --short`

Notes:
- macOS 26.5 (Build 25F71)
- Kernel: Darwin 25.5.0 arm64
- CPU: Apple M1, Memory: 16 GB
- Xcode CLI tools path: `/Library/Developer/CommandLineTools`
- Branch: `main`
- HEAD: `19513127e166de298581179b78e8252cab694ed7`
- Worktree was cleaned before final connection validation; `git status --short` returned no changes.

## 2) Python Runtime Readiness

Commands run:
- [x] `python3 --version`
- [x] `/opt/homebrew/bin/python3.12 --version` (if present)
- [ ] `/opt/homebrew/bin/python3.12 -m venv .venv`
- [x] `.venv/bin/python -m pip install -e .`
- [x] `.venv/bin/python -m unittest discover -s tests -q`
- [x] `.venv/bin/python -m devflow --help`

Result:
- [x] PASS
- [ ] FAIL

Failure details/remediation:
- `python3` is `3.14.0` and worked for current checks.
- `/opt/homebrew/bin/python3.12` is not present on this machine.
- Test suite result: 43 tests passed.
- CLI help output confirmed working entrypoint.

## 3) VS Code Readiness

Checks:
- [ ] VS Code opens workspace at repo root
- [ ] Copilot chat/code actions available
- [ ] integrated terminal starts at repo root
- [x] required docs are present:
  - [x] `docs/workflows/local-worker-health-check-runbook.md`
  - [x] `docs/workflows/hello-peer-orchestrator-vscode.md`
  - [x] `docs/workflows/vscode-smoke-audit-handoff.md`

Notes:
- `code` CLI is not installed in PATH (`command not found`).
- Manual in-editor checks are still required for VS Code/Copilot UI readiness.

## 4) Local Worker Preflight

Commands run:
- [x] `bash scripts/local_models_doctor.sh`
- [x] `curl -sS http://127.0.0.1:11434/api/version`
- [x] `curl -sS http://127.0.0.1:11434/api/tags`
- [x] `python3 scripts/local_agent_runner.py "Return only: LOCAL_WORKER_OK"`
- [x] `python3 scripts/local_agent_runner.py "You are a coder. Return exactly CONNECTED_CODER_OK"`
- [x] `python3 scripts/local_agent_runner.py "You are a reviewer. Return exactly CONNECTED_REVIEWER_OK"`

Expected token observed:
- [x] `LOCAL_WORKER_OK`

Result:
- [x] PASS
- [ ] FAIL
- [ ] BLOCKED (model still downloading)

Failure details/remediation:
- Active profile auto-detected as `mini`.
- Correct model target for this machine: `qwen2.5-coder:14b`.
- Installed model list includes `qwen2.5-coder:14b` (size ~9.0 GB), which matches the preferred `mini` profile.
- Installed fallback list also includes `qwen2.5-coder:7b-instruct` (size ~4.7 GB) for memory-constrained runs.
- Ollama API reachable at `http://127.0.0.1:11434` (version `0.13.0`).
- Role probes passed with exact responses `CONNECTED_CODER_OK` and `CONNECTED_REVIEWER_OK`.

## 5) VS Code Smoke Audit

Runbook:
- [ ] `docs/workflows/vscode-smoke-audit-handoff.md`

Verification rerun command:
- [x] `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s smoke_todo_cli/tests -q`

Audit result:
- [ ] PASS
- [ ] FAIL
- [x] BLOCKED

Findings:
- Smoke project path is not present in this workspace (`smoke_todo_cli/tests` missing).
- To complete this section, open the smoke proving repo/workspace that contains `smoke_todo_cli` and rerun the audit command.

## 6) Hardening Notes (Optional)

Machine-specific caveats:
- 

Repeatable fixes added to shared docs:
- 

## 7) Final Sign-Off

Checklist:
- [x] tests pass in `.venv`
- [x] `devflow` CLI works from VS Code terminal
- [x] local worker probe passes
- [ ] smoke audit recorded
- [ ] this setup log is complete

Sign-off note:
- 
