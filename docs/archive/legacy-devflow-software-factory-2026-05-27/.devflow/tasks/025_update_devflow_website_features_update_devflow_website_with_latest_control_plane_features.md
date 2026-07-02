# Task: 025_update_devflow_website_features - Update devflow website with latest control-plane features
Status: CLAIMED
Goal: devflow_marketing_refresh
Plan: docs/plans/2026-05-27-devflow-agentic-control-plane-implementation-plan.md
Assigned Agent: vscode
Owner Lock: vscode-website-update-025
Risk: LOW
Branch: devflow/task-025_update_devflow_website_features-vscode
Touched Files:
- public/index.html
- public/styles.css
- public/app.js
- tests/test_marketing_assets.py
- .devflow/tasks/025_update_devflow_website_features_update_devflow_website_with_latest_control_plane_features.md
- .devflow/reports/025_update_devflow_website_features.report.md

## 1. Objective

Refresh the static `public/` devflow website so it reflects the current control-plane features: artifacts, context packs, local review workers, diff-only implementation, repair/TDD states, DAG/impact analysis, traces/evals, worktrees, architectural memory invalidation, and the consolidated `/devflow` VS Code workflow.

## 2. Allowed Files

- public/index.html
- public/styles.css
- public/app.js
- tests/test_marketing_assets.py
- .devflow/tasks/025_update_devflow_website_features_update_devflow_website_with_latest_control_plane_features.md
- .devflow/reports/025_update_devflow_website_features.report.md

## 3. Do Not Touch

- .env
- production secrets
- unrelated files outside Allowed Files

## 4. Required Context



## Process Incident & Auto-Recovery Fix

On 2026-05-27, Copilot began direct implementation before running local-worker preflight or delegating bounded drafting/review to the local model. This violated the Devflow workflow and token-saving architecture. Implementation was frozen until local-worker preflight passed or manual mode was explicitly approved.

### Root Cause
Ollama API was not reachable on 127.0.0.1:11434. The system did not attempt auto-recovery, and a stale Docker container prevented new launches.

### Fix & New Workflow
- Added sequential auto-recovery to scripts/local_models_doctor.sh: attempts native app launch, then Docker, with retries and clear logging.
- Handles Docker container name conflicts automatically.
- If all recovery fails, user is prompted with actionable instructions.
- All failures and recovery attempts are logged for traceability.

### Outcome
Auto-recovery succeeded: Docker-based Ollama is now running, API is reachable, and local-worker preflight passes (LOCAL_WORKER_OK).

Process observations to address after this workflow test:
- `.devflow/context/repo-map.short.md` was expected by the workflow but missing at task start, so targeted reads/searches replaced the repo-map context path.
- The `/devflow` skill mentions `using-superpowers` as a companion workflow, but the user still needed confirmation; surfacing that dependency more explicitly in the slash-command text would reduce ambiguity.
- The first task-creation terminal call was interrupted while adding this observations requirement, which left no partial task file; a resumable or more visible task-creation step would be helpful.
- The generated task filename is long and wraps in terminal output, making it harder to copy into follow-up commands.
- The task scaffold leaves Objective/Context/Instructions blank; for workflow test tasks, a richer scaffold template could reduce manual packet editing.

## 5. Implementation Instructions

1. Update hero and page copy to position devflow as a Git-and-artifact-native control plane.
2. Add feature sections for implemented control-plane slices and the `/devflow` workflow surface.
3. Update the simulator steps/logs to include context packs, artifacts, memory invalidation, traces/evals, and reports.
4. Keep the existing static vanilla asset model and narrow visual language.
5. Verify the static assets and marketing asset tests.

## 6. Patch Protocol

Unified diff only.

## 7. Verification Commands

- test -f public/index.html && test -f public/styles.css && test -f public/app.js && PYTHONPATH=src python3 -m unittest tests.test_marketing_assets -q

## 8. Failure Handling

- Patch apply failure: stop and report
- Protected file touched: stop immediately
- Verification failure: rollback and report

## 9. Execution Results

```diff
# Add unified diff here.
```

## 10. Final Report

Pending.
