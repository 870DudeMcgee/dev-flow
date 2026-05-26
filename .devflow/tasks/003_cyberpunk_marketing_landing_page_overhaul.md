# Task: 003 - Cyberpunk marketing landing page overhaul
Status: CLAIMED
Goal: 
Plan: 2026-05-26-devflow-marketing-cyberpunk-plan.md
Assigned Agent: antigravity
Owner Lock: antigravity-mini-session
Risk: LOW
Branch: devflow/task-003-antigravity
Touched Files:
- public/styles.css
- public/index.html
- public/app.js
- 

## 1. Objective

Describe the concrete outcome for this task.

## 2. Allowed Files

- 

## 3. Do Not Touch

- .env
- production secrets
- unrelated files outside Allowed Files

## 4. Required Context

Add relevant architecture notes, file excerpts, or decisions.

## 5. Implementation Instructions

Describe the implementation steps for the owning orchestrator.

## 6. Patch Protocol

Unified diff only.

## 7. Verification Commands

- PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -q

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
