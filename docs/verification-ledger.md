# Verification Ledger

Date: 2026-06-16
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

## Milestone 26 Operational Baseline / Trust Pass

- Scratch daily shell loop: passed on 2026-06-16.
  - Entry point: `env PYTHONPATH=<repo-root>/src:<repo-root> <repo-root>/.venv/bin/python -m devflow.cli`.
  - Scratch root: `/var/folders/rl/9__qbthj5pj3s5xszbnfzsq40000gn/T//devflow-m26.SW5Xi6`.
  - Covered commands: `init`, `doctor`, `dashboard`, `task create`, `task run --worker shell`, workspace isolation checks, `task verify`, `task list`, `task show`, second `dashboard`, `task promote-preview`, `task promote`, final `task show`, final `dashboard`, and `git status --short` from the real repo.
  - Result: `task-0001` reached `promoted`; `result.txt` was absent from the scratch project root before promotion, present only under `.devflow/workspaces/task-0001/result.txt`, then present in the scratch root after promotion.
  - Real repo after proof: dirty only from the intentional Milestone 26 code, tests, docs, and handoff edits.
- Focused repair evidence after the proof exposed a copy-workspace promotion bug: passed, `39 passed in 25.01s`.
  - Command: `PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_promote_preview.py tests/test_git_worktree_promotion.py tests/test_operating_layer.py::test_operating_layer_server_runs_approved_task_promotion -q`.
  - Scope: non-git scratch promotion, copy-workspace promotion approval semantics, dirty/stale Git guards, deletion confirmation, Git-native promotion flow, and browser-approved promotion execution.
  - Boundary confirmation: no public APIs, new workers, adapters, routing, databases, auto-resume, auto-promotion, provider calls, push, or pull-request automation were added.

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

- Browser control-room verification fast path: passed, `11 passed in 23.69s`.
  - Command: `PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_operator_ui_browser.py --durations=10 -k "browser_model_catalog_hydrates_from_snapshot_without_agents_fetch_on_first_load or browser_model_catalog_falls_back_to_agents_when_snapshot_catalog_is_empty_or_missing or local_model_inventory_and_dropdown_show_fake_ollama_models or builder_judge_model_pickers_update_hidden_inputs_with_keyboard or home_prioritizes_brainstorm_workbench_without_closed_history_noise or home_exposes_idea_to_task_flow_and_task_control or product_stage_contains_task_launchpad_review_and_evidence or pipeline_spine_buttons_do_not_overlap or visible_controls_and_primary_cards_fit_without_horizontal_clipping or idea_greenhouse_lanes_wrap_at_mobile_width"`.
  - Scope: lean-only browser fixtures that validate smoke/layout and model-catalog API behavior without rich seeding.
  - Proof tier: lightweight browser smoke proof.
- Rich seeded control-room baseline for interaction/layout regression: passed, `2 passed in 10.27s`.
  - Command: `PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_operator_ui_browser.py --durations=10 -k "test_idea_greenhouse_shows_lane_header_and_useful_card_height or test_home_shell_is_compact_and_topbar_health_replaces_side_panel"`.
  - Scope: representative seeded controls and layout checks that still require the full fixture.
- Browser control-room regression proof (rich seeded, interaction-heavy): passed, `1 passed in 6.23s` (single test command sample).
  - Command: `PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_operator_ui_browser.py --durations=10 -k "test_worker_row_selects_launchpad_and_runs_inline_shell_worker"`.
  - Scope: seeded task lifecycle and runtime action surface remain covered under the rich fixture.
- Browser control-room visual QA: passed.
  - Command: `PYTHONPATH=src:. .venv/bin/devflow operating-layer visual-qa --json`.
  - Proof tier: fast automated screenshot/probe pass for desktop+mobile with current evidence.

- Brainstorm workbench + advisory chat UI: passed, `80 passed, 11 skipped, 2 warnings in 82.19s`.
  - Command: `PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_brainstorm_workbench.py tests/test_agent_registry.py tests/test_configured_model_advisory.py tests/test_operating_layer.py tests/test_operator_ui_browser.py -q`.
  - Scope: advisory brainstorm profile, missing-key failure without fake assistant output, mocked chat transcript evidence, spec/plan/task escalation artifacts, operating-layer API/UI contracts, registry visibility, and browser UI selectors.
- Premium brainstorm workbench layout repair: passed, `44 passed, 11 skipped, 2 warnings in 74.69s`.
  - Command: `PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_operating_layer.py tests/test_operator_ui_browser.py -q`.
  - Scope: preview-like dark sidebar/topbar plus light chat/pipeline workbench, guided first viewport, browser selectors, responsive overflow checks, and task/review/evidence controls.
- Brainstorm registry/dogfood after layout repair: passed, `58 passed in 83.79s`.
  - Command: `PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_brainstorm_workbench.py tests/test_agent_registry.py tests/test_configured_model_advisory.py tests/test_dogfood_harness.py -q`.
- Brainstorm workbench visual QA: passed.
  - Command: `PYTHONPATH=src:. .venv/bin/devflow operating-layer visual-qa --json`.
  - Flow covered: Brainstorm chat, Pipeline stages, Worker lanes, Review queue, Evidence stream, guided first viewport, desktop/mobile screenshot paths, and no horizontal overflow.
- Dogfood harness metadata after brainstorm workbench: passed, `22 passed in 80.33s`.
  - Command: `PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_dogfood_harness.py -q`.
- Live in-app browser smoke for brainstorm workbench: passed on `http://127.0.0.1:8766/#orchestrator`.
  - Observed: Home route opens at the top of the chat-first workbench, advisory model label is visible, pipeline escalation controls are visible, operations tray follows below, desktop/mobile have no horizontal overflow, and browser console warnings/errors are empty.
- Live in-app browser smoke after canonical UI doc refresh: passed on `http://127.0.0.1:8765/?cb=1781740983094`.
  - Observed: cache-busted URL opened `Dev-Flow Operating Layer`; DOM markers included `Brainstorm`, `Pipeline`, `Worker lanes`, `Review queue`, and `Evidence stream`; old static marketing marker `The Git-native control plane for bounded agent work` was absent.
- Prior idea-intake UI simplification, now superseded by the brainstorm workbench first viewport: passed, `65 passed in 18.81s`.
  - Command: `PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_operating_layer.py tests/test_supervisor_operating_surface.py -q`.
  - Scope: guided idea intake, approved browser idea capture, simplified navigation, browser mutation policy, task/run/verify/promote guards, and supervisor policy.
- Prior operating-layer visual QA after intake simplification, now superseded by the brainstorm workbench visual QA above: passed.
  - Command: `PYTHONPATH=src:. .venv/bin/devflow operating-layer visual-qa --json`.
  - Flow covered: prior idea-intake controls, guided first viewport, active work cards, approval states, Advanced Commands containment, desktop/mobile screenshot paths, and no horizontal overflow.
- Dogfood harness visual metadata checks after intake simplification: passed, `21 passed in 45.42s`.
  - Command: `PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_dogfood_harness.py -q`.
- Prior live in-app browser smoke after intake simplification, now superseded by the brainstorm workbench smoke above: passed on `http://127.0.0.1:8766/#projects`.
  - Observed: five-item nav (`Home`, `Work`, `Review`, `Projects`, `Advanced`), only guided + Projects visible on the Projects route after app settle, prior idea text area visible, immediate task creation tucked behind details, no horizontal overflow, and no browser console errors.
- Browser control-room usability + core controls: passed, `84 passed in 66.53s`.
  - Command: `PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_operating_layer.py tests/test_supervisor_operating_surface.py tests/test_dogfood_harness.py -q`.
  - Scope: guided browser sections, approved task creation, approved shell worker run, verification/promotion gates, supervisor browser policy, and operating-layer dogfood metadata.
- Operating-layer visual QA plan/checks: passed.
  - Command: `PYTHONPATH=src:. .venv/bin/devflow operating-layer visual-qa --json`.
  - Flow covered: guided first viewport, active work cards, approval states, Advanced Commands containment, desktop/mobile screenshot paths, and no horizontal overflow.
- Earlier live in-app browser smoke before brainstorm workbench: passed on `http://127.0.0.1:8766`.
  - Observed: the then-current first surface, no horizontal overflow, six active-work groups, one task card in the current repo snapshot, Advanced Commands preview with readable safety text plus raw safety class, and no browser console errors.
