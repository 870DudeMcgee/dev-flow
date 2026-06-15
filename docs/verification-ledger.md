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

## Focused Operating-Layer Evidence

- Browser idea intake + UI simplification: passed, `65 passed in 18.81s`.
  - Command: `PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_operating_layer.py tests/test_supervisor_operating_surface.py -q`.
  - Scope: guided idea intake, approved browser idea capture, simplified navigation, browser mutation policy, task/run/verify/promote guards, and supervisor policy.
- Operating-layer visual QA plan/checks after intake simplification: passed.
  - Command: `PYTHONPATH=src:. .venv/bin/devflow operating-layer visual-qa --json`.
  - Flow covered: Capture idea, guided first viewport, active work cards, approval states, Advanced Commands containment, desktop/mobile screenshot paths, and no horizontal overflow.
- Dogfood harness visual metadata checks after intake simplification: passed, `21 passed in 45.42s`.
  - Command: `PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_dogfood_harness.py -q`.
- Live in-app browser smoke after intake simplification: passed on `http://127.0.0.1:8766/#projects`.
  - Observed: five-item nav (`Home`, `Work`, `Review`, `Projects`, `Advanced`), only guided + Projects visible on the Projects route after app settle, idea textarea visible, immediate task creation tucked behind details, no horizontal overflow, and no browser console errors.
- Browser control-room usability + core controls: passed, `84 passed in 66.53s`.
  - Command: `PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_operating_layer.py tests/test_supervisor_operating_surface.py tests/test_dogfood_harness.py -q`.
  - Scope: guided browser sections, approved task creation, approved shell worker run, verification/promotion gates, supervisor browser policy, and operating-layer dogfood metadata.
- Operating-layer visual QA plan/checks: passed.
  - Command: `PYTHONPATH=src:. .venv/bin/devflow operating-layer visual-qa --json`.
  - Flow covered: guided first viewport, active work cards, approval states, Advanced Commands containment, desktop/mobile screenshot paths, and no horizontal overflow.
- Live in-app browser smoke: passed on `http://127.0.0.1:8766`.
  - Observed: guided first operating section, no horizontal overflow, six active-work groups, one task card in the current repo snapshot, Advanced Commands preview with readable safety text plus raw safety class, and no browser console errors.
