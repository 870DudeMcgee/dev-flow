# Verification Ledger

Date: 2026-06-15
Status: Active verification reference

Use this ledger before running expensive verification. If the question can be answered from recent evidence plus lightweight read-only checks, do not rerun full pytest or dogfood.

## Latest Broad Evidence

- Full pytest: passed, `1058 passed, 6 skipped in 185.62s`.
  - Evidence source: observed baseline evidence from the 2026-06-15 operational-baseline session.
  - Persisted log: none found in the active checkout during the baseline pass.
  - Reuse policy: treat as current broad-suite evidence until shared behavior changes, release readiness is requested, or the user explicitly asks for a full-suite rerun.
- Production-readiness dogfood: passed, `153/155`, `Bulletproof candidate`.
  - Evidence path: `.devflow/dogfood/runs/dogfood-20260615T165239Z/report.md`.
  - Scorecard path: `.devflow/dogfood/runs/dogfood-20260615T165239Z/scorecard.yaml`.
  - Duration: `8.908s`.
  - Boundary confirmation: no provider API calls, autonomous routing, auto-promotion, push, database, vector DB/RAG/embeddings, dashboard/daemon, or ML training.

## Verification Escalation Rule

- Status questions: use lightweight read-only commands plus this ledger.
- Documentation-only changes: run `git diff --check` and targeted stale-context searches.
- Focused code changes: run the smallest meaningful targeted tests around the touched behavior.
- Full pytest: reserve for release gates, broad shared behavior changes, or an explicit user request.
- Dogfood: reuse the latest passing score unless the change touches dogfood logic, control-room end-to-end flow, operating-layer behavior, or release readiness.

## Current Baseline Notes

- `main` was clean and in sync with `origin/main` before the operational-baseline edits began.
- `devflow doctor` initially failed because macOS hidden flags were set on local `.venv` paths; this has been downgraded to non-blocking local environment hygiene so it does not read as product failure.
- If the generated `.venv/bin/devflow` entrypoint cannot import the editable install because the `.pth` file itself is hidden, clear the local flag with `chflags -R nohidden .venv` or invoke with `PYTHONPATH=src:.`.
- `dashboard`, `scheduler`, `freshness`, and `goal` surfaces now agree that goal lifecycle state is missing for `G-0001` through `G-0004`; the remaining repair is an operator lifecycle decision, not automatic mutation.
