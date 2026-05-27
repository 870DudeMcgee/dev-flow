from __future__ import annotations

import json
import os
import sys

from devflow.admin_commands import write_orchestrator_templates


def init_workspace_command(default_config: dict, constitution_text: str) -> None:
    folders = [
        "goals",
        "plans",
        "tasks",
        "workflows",
        "skills",
        "context",
        "index",
        "logs",
        "reports",
        "artifacts",
        "orchestrators",
        "worktrees",
        "memory",
        os.path.join("workflow"),
        os.path.join("skills", "devflow-software-factory", "resources", "schemas"),
        os.path.join("hooks"),
    ]
    os.makedirs(".devflow", exist_ok=True)
    for folder in folders:
        os.makedirs(os.path.join(".devflow", folder), exist_ok=True)

    config_path = os.path.join(".devflow", "config.json")
    with open(config_path, "w", encoding="utf-8") as handle:
        json.dump(default_config, handle, indent=2)

    constitution_path = os.path.join(".devflow", "constitution.md")
    with open(constitution_path, "w", encoding="utf-8") as handle:
        handle.write(constitution_text)

    write_orchestrator_templates()

    print("Initialized empty devflow workspace in .devflow/")


def status_workspace_command() -> None:
    if not os.path.exists(".devflow"):
        print("Error: .devflow/ folder not found. Run 'devflow init' first.")
        sys.exit(1)

    goals = os.listdir(".devflow/goals") if os.path.isdir(".devflow/goals") else []
    plans = os.listdir(".devflow/plans") if os.path.isdir(".devflow/plans") else []
    tasks = os.listdir(".devflow/tasks") if os.path.isdir(".devflow/tasks") else []

    statuses = {
        "PENDING": 0,
        "CLAIMED": 0,
        "PREVIEWED": 0,
        "RUNNING": 0,
        "COMPLETED": 0,
        "FAILED": 0,
        "BLOCKED": 0,
    }
    for task_name in tasks:
        if not task_name.endswith(".md"):
            continue
        with open(os.path.join(".devflow/tasks", task_name), "r", encoding="utf-8") as handle:
            content = handle.read()
        for state in statuses:
            if f"Status: {state}" in content:
                statuses[state] += 1
                break

    print("devflow status")
    print(f"- goals: {len(goals)}")
    print(f"- plans: {len(plans)}")
    print(f"- tasks: {len([task for task in tasks if task.endswith('.md')])}")
    for key in ("PENDING", "CLAIMED", "PREVIEWED", "RUNNING", "COMPLETED", "FAILED", "BLOCKED"):
        print(f"- {key.lower()}: {statuses[key]}")


def impact_command_impl(task_file: str, cwd: str) -> None:
    from devflow.impact import analyze_impact

    try:
        report = analyze_impact(task_file, cwd)
    except FileNotFoundError as exc:
        print(f"Error: {exc}")
        sys.exit(1)
    except Exception as exc:
        print(f"Error analyzing impact: {exc}")
        sys.exit(1)

    print(f"Impact Analysis Report for Task {report.get('task_id')} - {report.get('title')}")
    print("======================================================================")
    print(f"Risk Level: {report.get('risk_level')} (score: {report.get('risk_score')})")
    print("Allowed Files:")
    for allowed_file in report.get("allowed_files", []):
        print(f"  - {allowed_file}")
    if report.get("touched_files"):
        print("Touched Files:")
        for touched_file in report.get("touched_files", []):
            print(f"  - {touched_file}")

    print("\nWorkspace Import Usages:")
    usages = report.get("public_interface_usages", [])
    if not usages:
        print("  None detected (no external files import these modules).")
    else:
        for usage in usages:
            print(f"  - {usage}")

    print("\nGit History Co-mutations (frequently changed together):")
    co_mutations = report.get("co_mutations", [])
    if not co_mutations:
        print("  None detected.")
    else:
        for co_mutation in co_mutations:
            print(f"  - {co_mutation}")

    print("\nVerification Targets (relevant tests to run):")
    tests = report.get("verification_targets", [])
    if not tests:
        print("  None detected.")
    else:
        for test in tests:
            print(f"  - {test}")

    if report.get("suggests_split"):
        print("\nWARNING: Task Split Recommended!")
        print(f"Reason: {report.get('split_reason')}")
