from __future__ import annotations

import os
import sys


def _orchestrator_template(name: str) -> str:
    return f"""# {name} Peer Orchestrator Template

Role: Peer Orchestrator

## Purpose

Operate as a complete AI development team for claimed devflow tasks.

## Internal Dev Team

- Product/Spec Analyst
- Technical Architect
- Task Planner
- Diff Implementer
- Test Engineer
- Verifier/Reviewer
- Release/Report Coordinator

## Operating Rules

- Claim a task before mutating its task file or touched-file scope.
- Treat other claimed tasks as read-only unless ownership is transferred.
- Use local models as bounded worker subagents when useful.
- Do not assume permanent global role ownership.
- Do not bypass devflow run safety gates.
- Write reports and keep task status current.

## Handoff Expectations

- Task Markdown remains the canonical task state.
- plan.json mirroring is best-effort only.
- Reports must be sufficient for another orchestrator to audit or continue work.
"""


def _local_model_worker_policy() -> str:
    return """# Local Model Worker Policy

Local models are worker subagents for peer orchestrators.

They may help with:

- patch drafting
- test generation
- failure explanation
- small repair loops
- summarization

They must not mutate repo state directly.

All local-model outputs should flow back through an orchestrator, then through task files, unified diffs, verification, and reports.

Current preferred endpoint:

- http://127.0.0.1:11434

Candidate models:

- qwen2.5-coder:1.5b
- qwen2.5-coder:7b-instruct (fast fallback for constrained 16 GB machines)
- qwen2.5-coder:14b (preferred coding worker for Mac mini M1 16 GB)
- qwen2.5-coder:32b-instruct
"""


def write_orchestrator_templates() -> None:
    templates = {
        "codex.md": _orchestrator_template("Codex Desktop"),
        "vscode-copilot.md": _orchestrator_template("VS Code/Copilot"),
        "antigravity.md": _orchestrator_template("Antigravity"),
        "local-model-worker-policy.md": _local_model_worker_policy(),
    }
    root = os.path.join(".devflow", "orchestrators")
    os.makedirs(root, exist_ok=True)
    for filename, content in templates.items():
        path = os.path.join(root, filename)
        if not os.path.exists(path):
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(content)


_UNIVERSAL_FILES = [
    "AGENTS.md",
    ".devflow/workflow/DEVFLOW_WORKFLOW.md",
    ".devflow/workflow/token-policy.md",
    ".devflow/workflow/artifact-contract.md",
    ".devflow/workflow/role-contracts.md",
    ".devflow/workflow/verification-policy.md",
    ".devflow/skills/devflow-software-factory/SKILL.md",
]

_VSCODE_FILES = [
    ".github/copilot-instructions.md",
    ".github/instructions/devflow.instructions.md",
    ".github/prompts/devflow-plan.prompt.md",
    ".github/prompts/devflow-implement.prompt.md",
    ".github/prompts/devflow-review.prompt.md",
    ".github/prompts/devflow-repair.prompt.md",
]

_ANTIGRAVITY_FILES = [
    ".antigravity/rules.md",
    ".antigravity/workflows/devflow.md",
]

_CODEX_FILES = [
    "AGENTS.md",
    ".devflow/skills/devflow-software-factory/SKILL.md",
    ".codex/optional-project-notes.md",
]

_CODEX_HOME_FILES = [
    "~/.codex/AGENTS.md",
]


def _check_file(path: str) -> str:
    expanded = os.path.expanduser(path)
    if os.path.exists(expanded):
        return "✅"
    return "❌"


def _check_home_file(path: str) -> str:
    expanded = os.path.expanduser(path)
    if os.path.exists(expanded):
        return "✅"
    return "⚠️"


def doctor_command_impl() -> None:
    all_ok = True

    print("Universal:")
    for path in _UNIVERSAL_FILES:
        status = _check_file(path)
        print(f"  {status} {path}")
        if status == "❌":
            all_ok = False

    print("\nVS Code:")
    for path in _VSCODE_FILES:
        status = _check_file(path)
        print(f"  {status} {path}")
        if status == "❌":
            all_ok = False

    print("\nAntigravity:")
    for path in _ANTIGRAVITY_FILES:
        status = _check_file(path)
        print(f"  {status} {path}")
        if status == "❌":
            all_ok = False

    print("\nCodex:")
    for path in _CODEX_FILES:
        status = _check_file(path)
        print(f"  {status} {path}")
        if status == "❌":
            all_ok = False
    for path in _CODEX_HOME_FILES:
        status = _check_home_file(path)
        print(f"  {status} {path}")

    print()
    if all_ok:
        print("All adapter files present.")
    else:
        print("Some adapter files are missing. Run 'devflow init-adapters --all' to generate them.")
        sys.exit(1)


def _agents_md_content() -> str:
    return '''# Devflow Agent Operating Rule

This repository uses the **Devflow Software Factory** workflow.

Before modifying code, you MUST follow this sequence:

1. Understand the task.
2. Identify the smallest relevant context.
3. Create or update a `.devflow/tasks/<task-id>.md` task packet unless the user explicitly requests a trivial one-shot edit.
4. State the planned files and verification command before implementation.
5. Prefer tests first for behavior changes.
6. Emit minimal diffs only.
7. Never modify files outside the task's allowed path list.
8. Run or request verification before declaring success.
9. Write a short completion report with: files changed, tests run, risks, follow-up tasks.

For details, read:
- `.devflow/workflow/DEVFLOW_WORKFLOW.md`
- `.devflow/workflow/token-policy.md`
- `.devflow/skills/devflow-software-factory/SKILL.md`

Follow **PLAN → CONTEXT → TEST → IMPLEMENT → VERIFY → REVIEW → REPORT**.

## Token Policy

Use the smallest sufficient context.
Do not read the whole repository unless the task explicitly requires architectural analysis.

## Safety Policy

All code changes are untrusted proposals until validated.
Protected files require explicit user approval.

## Parallel Coordination

This repository supports three peer orchestrators: Codex, VS Code/Copilot, Antigravity.
Coordination is decentralized via task markdown metadata, checkpoint branches, and reports.
'''


def _copilot_instructions_content() -> str:
    return '''# GitHub Copilot Instructions

This repository uses the **Devflow Software Factory** workflow.

Before making non-trivial code changes:

1. Read `AGENTS.md`.
2. Follow `.devflow/workflow/DEVFLOW_WORKFLOW.md` if the task involves code, tests, refactors, architecture, or bug fixes.
3. Use the smallest sufficient context.
4. Do not scan the entire repository unless the task requires architecture-level analysis.
5. Prefer task packets in `.devflow/tasks/`.
6. Prefer red/green/repair for behavior changes.
7. Emit minimal diffs.
8. Run or request verification.
9. Finish with a report.

Do not perform unrelated cleanup.
Do not change protected files without explicit user approval.
Do not claim tests passed unless they were actually run.
'''


def _devflow_instructions_content() -> str:
    return '''---
applyTo: "**"
---

# Devflow Workflow Enforcement

For any non-trivial software task, use:

**PLAN → CONTEXT → TEST → IMPLEMENT → VERIFY → REVIEW → REPORT**

## Required behavior

- Minimize context.
- Prefer existing repo maps and task packets.
- State intended files before changing them.
- Keep diffs narrow.
- Avoid dependency changes.
- Avoid protected files.
- Verify before claiming success.
'''


def _prompt_plan_content() -> str:
    return '''# Devflow Plan

Use the Devflow workflow.

Given the user\'s goal, produce a minimal implementation plan.

Return:

1. Task classification
2. Proposed task packet
3. Allowed files
4. Context needed
5. Tests to add or run
6. Risk tier
7. Verification command
8. Smallest next action

Do not write code yet.
'''


def _prompt_implement_content() -> str:
    return '''# Devflow Implement

Use the Devflow workflow. Implement the task from its packet.

Rules:

1. Only touch allowed files listed in the task packet.
2. Emit minimal unified diff.
3. No unrelated cleanup.
4. No dependency changes without approval.
5. No protected file changes without approval.
6. Run targeted verification after implementation.
7. Stop if files outside allowed paths are required.
8. Report files changed, tests run, and verification result.
'''


def _prompt_review_content() -> str:
    return '''# Devflow Review

Review the current diff under the Devflow workflow.

Check: task compliance, scope creep, protected file changes, missing tests, verification gaps, simpler alternatives.

Return a JSON review result with status, blocking_findings, non_blocking_findings, verification_required, and summary.
'''


def _prompt_repair_content() -> str:
    return '''# Devflow Repair

Use the Devflow workflow as repair agent.

Rules:

1. Read only the latest failure summary, the current diff, and touched files.
2. Classify the failure type.
3. Make the smallest possible repair.
4. Do not redesign or refactor.
5. Run targeted verification after repair.
6. Stop after the repair budget is exhausted.
7. Report the failure classification, repair applied, and verification result.
'''


def _antigravity_rules_content() -> str:
    return '''# Antigravity Rules: Devflow Software Factory

All Antigravity agents working in this repository must follow the Devflow workflow.

For non-trivial changes:

1. Read `AGENTS.md`.
2. Read `.devflow/workflow/DEVFLOW_WORKFLOW.md`.
3. Create or update a task packet in `.devflow/tasks/`.
4. Build minimal context.
5. Plan before editing.
6. Prefer tests first.
7. Implement minimal diff.
8. Verify.
9. Review.
10. Report.
'''


def _antigravity_workflow_content() -> str:
    return '''# /devflow

Use this workflow for any software engineering task.

Steps: Intake → Task packet → Context → Plan checkpoint → Test-first → Implement → Verify → Review → Report.

See `.devflow/workflow/DEVFLOW_WORKFLOW.md` for full details.
'''


def _codex_notes_content() -> str:
    return '''# Codex Project Notes

This repository uses the **Devflow Software Factory** workflow.

Codex should follow `AGENTS.md` as the primary instruction source.
For non-trivial tasks, use the `devflow-software-factory` skill.
Follow PLAN → CONTEXT → TEST → IMPLEMENT → VERIFY → REVIEW → REPORT.
'''


_ADAPTER_GENERATORS: dict[str, list[tuple[str, object]]] = {
    "vscode": [
        (".github/copilot-instructions.md", _copilot_instructions_content),
        (".github/instructions/devflow.instructions.md", _devflow_instructions_content),
        (".github/prompts/devflow-plan.prompt.md", _prompt_plan_content),
        (".github/prompts/devflow-implement.prompt.md", _prompt_implement_content),
        (".github/prompts/devflow-review.prompt.md", _prompt_review_content),
        (".github/prompts/devflow-repair.prompt.md", _prompt_repair_content),
    ],
    "antigravity": [
        (".antigravity/rules.md", _antigravity_rules_content),
        (".antigravity/workflows/devflow.md", _antigravity_workflow_content),
    ],
    "codex": [
        (".codex/optional-project-notes.md", _codex_notes_content),
    ],
    "universal": [
        ("AGENTS.md", _agents_md_content),
    ],
}


def init_adapters_command_impl(targets: list[str] | None = None, force: bool = False) -> None:
    if targets is None or "all" in targets:
        targets = ["universal", "vscode", "antigravity", "codex"]

    created = 0
    skipped = 0
    for target in targets:
        generators = _ADAPTER_GENERATORS.get(target, [])
        if not generators:
            print(f"Warning: unknown target '{target}', skipping.")
            continue
        for path, generator_fn in generators:
            if os.path.exists(path) and not force:
                print(f"  skip {path} (exists, use --force to overwrite)")
                skipped += 1
                continue
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(generator_fn())
            print(f"  wrote {path}")
            created += 1

    print(f"\nAdapter generation complete: {created} created, {skipped} skipped.")
