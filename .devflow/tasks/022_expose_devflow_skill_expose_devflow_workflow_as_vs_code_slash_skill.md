# Task: 022_expose_devflow_skill - Expose Devflow workflow as VS Code slash skill
Status: COMPLETED
Goal: vscode_devflow_invocation
Plan:
Assigned Agent: vscode
Owner Lock: copilot-2026-05-27-devflow-skill
Risk: LOW
Branch: devflow/task-022_expose_devflow_skill-vscode
Touched Files:
- .github/skills/devflow/SKILL.md
- README.md
- docs/agent-handoff.md
- docs/roadmap.md

## 1. Objective

Expose the Devflow workflow as a discoverable VS Code/Copilot slash skill and document the invocation path.

## 2. Allowed Files

- .github/skills/devflow/SKILL.md
- README.md
- docs/agent-handoff.md
- docs/roadmap.md

## 3. Do Not Touch

- .env
- production secrets
- unrelated files outside Allowed Files

## 4. Required Context

- Workspace skills must live under `.github/skills/<name>/SKILL.md` for project-level slash-command discovery.
- The existing `.devflow/skills/devflow-software-factory/SKILL.md` remains the internal Devflow workflow reference.
- Existing focused prompts under `.github/prompts/` remain available for plan, implement, repair, and review flows.

## 5. Implementation Instructions

1. Add `.github/skills/devflow/SKILL.md` with `name: devflow` and `user-invocable: true`.
2. Reference the full workflow and CLI commands from the skill body.
3. Update README, handoff, and roadmap docs with the invocation surface.

## 6. Patch Protocol

Unified diff only.

## 7. Verification Commands

- PYTHONPATH=src python3 -m unittest tests/test_cli.py -q

## 8. Failure Handling

- Patch apply failure: stop and report
- Protected file touched: stop immediately
- Verification failure: rollback and report

## 9. Execution Results

```diff
# Add unified diff here.
```

## 10. Final Report

Completed.

- Added the `/devflow` workspace skill at `.github/skills/devflow/SKILL.md`.
- Documented slash invocation and focused prompt variants in `README.md`.
- Updated `docs/agent-handoff.md` and `docs/roadmap.md` with the VS Code/Copilot invocation surface.

Verification passed:
- `git diff --check`
- `PYTHONPATH=src python3 -m unittest tests/test_cli.py -q`
- `PYTHONPATH=src python3 -m devflow status`
