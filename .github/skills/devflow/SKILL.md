---
name: devflow
description: "Use when coordinating or executing the Devflow workflow in this repo. Triggers: devflow, DEVFLOW_WORKFLOW.md, workflow reference, task packet, claim task, VS Code, Copilot, Codex, Antigravity, PLAN CONTEXT TEST IMPLEMENT VERIFY REVIEW REPORT."
argument-hint: "Describe the task or goal to run through Devflow"
user-invocable: true
---

# Devflow Workflow

Use this skill to run repository work through the Devflow Software Factory workflow from VS Code/Copilot. This is the only user-facing Devflow slash command; planning, implementation, repair, and review modes are internal references loaded from this skill.

## When To Use

- The user invokes `/devflow` or asks for the Devflow workflow.
- The user mentions `DEVFLOW_WORKFLOW.md`, task packets, claims, reports, or peer coordination.
- The work should be coordinated across VS Code/Copilot, Codex, and Antigravity.
- The task is non-trivial software work: code, tests, docs, refactors, bug fixes, architecture, or workflow setup.

## Procedure

Follow `PLAN -> CONTEXT -> TEST -> IMPLEMENT -> VERIFY -> REVIEW -> REPORT`.

1. Read the smallest relevant workflow context first: `AGENTS.md`, `.devflow/workflow/DEVFLOW_WORKFLOW.md`, then the task packet or `.devflow/context/repo-map.short.md` when present.
2. Classify the task and risk tier.
3. For non-trivial work, create or update a task packet under `.devflow/tasks/` and claim it with the active orchestrator, normally `vscode` for Copilot in VS Code.
4. State allowed files, expected touched files, verification commands, and any protected-path concerns before editing.
5. Prefer tests first for behavior changes. For docs-only or customization-only work, choose a narrow verification command that proves the repo still loads or the relevant CLI still works.
6. **DELEGATE Code Generation & Repairs to Local Workers**: Never write implementation code, write tests, or perform repair loops in the cloud LLM. Instead:
   - Run the local model implementation CLI to draft the patch:
     `PYTHONPATH=src python3 -m devflow agent implement <task_file> --profile implementer`
   - Run the local model automated repair CLI to execute test-driven repair loops:
     `PYTHONPATH=src python3 -m devflow agent repair <task_file> --profile repair`
   - Read the generated JSON artifact from `.devflow/artifacts/<task_id>/` (`diff_result.json` or `repair_result.json`) to extract the proposed diff, write it to section 9 of the task markdown, and then run:
     `PYTHONPATH=src python3 -m devflow run <task_file> --yes`
7. Verify with the declared command, review for scope creep, and finish by publishing the report (.report.md) under `.devflow/reports/`.

## Mode References

Load one of these references only when that mode is needed:

- Plan mode: `./references/plan.md`
- Implement mode: `./references/implement.md`
- Repair mode: `./references/repair.md`
- Review mode: `./references/review.md`

Useful companion workflow skills:

- Use `using-superpowers` at the start of non-trivial work to choose the right process.
- Use `tdd` or `test-driven-development` for behavior changes with feasible tests.
- Use `diagnose` or `systematic-debugging` for unclear failures.
- Use `verification-before-completion` before reporting substantial work complete.

## Useful Commands

```bash
PYTHONPATH=src python3 -m devflow status
PYTHONPATH=src python3 -m devflow task new <task_id> "<task title>" --agent vscode --allowed <path> --verify "<command>"
PYTHONPATH=src python3 -m devflow task claim .devflow/tasks/<task_file>.md --agent vscode --lock <session-lock> --touch <path>
PYTHONPATH=src python3 -m devflow task status .devflow/tasks/<task_file>.md
PYTHONPATH=src python3 -m devflow run .devflow/tasks/<task_file>.md
PYTHONPATH=src python3 -m devflow run .devflow/tasks/<task_file>.md --yes
```

Use the installed console script as `devflow` when the editable environment is active.

## References

- Full workflow: `.devflow/workflow/DEVFLOW_WORKFLOW.md`
- Token policy: `.devflow/workflow/token-policy.md`
- Artifact contract: `.devflow/workflow/artifact-contract.md`
- Role contracts: `.devflow/workflow/role-contracts.md`
- Verification policy: `.devflow/workflow/verification-policy.md`