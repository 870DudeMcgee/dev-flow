# Task: 024_consolidate_devflow_slash_surface - Consolidate Devflow slash commands under one skill
Status: COMPLETED
Goal: vscode_single_devflow_slash_surface
Plan:
Assigned Agent: vscode
Owner Lock: copilot-2026-05-27-devflow-single-slash
Risk: LOW
Branch: devflow/task-024_consolidate_devflow_slash_surface-vscode
Touched Files:
- .github/prompts/devflow-plan.prompt.md
- .github/prompts/devflow-implement.prompt.md
- .github/prompts/devflow-repair.prompt.md
- .github/prompts/devflow-review.prompt.md
- .github/skills/devflow/SKILL.md
- .github/skills/devflow/references/plan.md
- .github/skills/devflow/references/implement.md
- .github/skills/devflow/references/repair.md
- .github/skills/devflow/references/review.md
- README.md
- docs/agent-handoff.md
- docs/roadmap.md

## 1. Objective

Collapse the visible VS Code/Copilot Devflow slash surface to one `/devflow` skill while preserving plan, implement, repair, and review guidance as skill references.

## 2. Allowed Files

- .github/prompts/devflow-*.prompt.md
- .github/skills/devflow/**
- README.md
- docs/agent-handoff.md
- docs/roadmap.md

## 3. Do Not Touch

- .env
- production secrets
- unrelated files outside Allowed Files

## 4. Required Context

- Prompt files under `.github/prompts/` appear as independent slash commands.
- Skill references under `.github/skills/devflow/references/` remain available to the skill without creating extra slash commands.
- The desired user-facing surface is one `/devflow` skill, similar to `/using-superpowers`.

## 5. Implementation Instructions

1. Delete standalone `.github/prompts/devflow-*.prompt.md` files.
2. Move their guidance into `.github/skills/devflow/references/`.
3. Update `.github/skills/devflow/SKILL.md` to describe plan, implement, repair, and review modes as internal references.
4. Update repo overview docs to describe the single slash-command surface.

## 6. Patch Protocol

Unified diff only.

## 7. Verification Commands

- git diff --check && PYTHONPATH=src python3 -m unittest tests/test_cli.py -q

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

- Deleted standalone Devflow prompt files from `.github/prompts/`.
- Added plan, implement, repair, and review references under `.github/skills/devflow/references/`.
- Updated `.github/skills/devflow/SKILL.md` so `/devflow` is the only user-facing Devflow slash command.
- Updated README, handoff, and roadmap docs to reflect the single-skill surface.

Verification passed:
- No `devflow-*.prompt.md` files remain.
- `.github/prompts/` is empty.
- `git diff --check`
- `PYTHONPATH=src python3 -m unittest tests/test_cli.py -q`
- `PYTHONPATH=src python3 -m devflow status`
