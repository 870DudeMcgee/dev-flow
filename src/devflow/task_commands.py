from __future__ import annotations

import json
import os
import re
import sys

from devflow.dag import TaskDAG
from devflow.manager import (
    build_task_template,
    claim_task_file,
    latest_report_for_task,
    load_all_plan_tasks,
    parse_task_file,
    plan_status_for_task,
    read_task_markdown,
    release_task_file,
    transition_task_file,
    verification_results_from_report,
)


def task_ready_command(json_output: bool = False, root_dir: str = ".") -> None:
    tasks = load_all_plan_tasks(root_dir)
    if not tasks:
        if json_output:
            print("[]")
        else:
            print("No tasks or plans found under .devflow/plans/.")
        return

    try:
        dag = TaskDAG(tasks, root_dir=root_dir)
    except ValueError as exc:
        print(f"Error building graph: {exc}")
        sys.exit(1)

    ready = dag.get_ready_tasks()
    if json_output:
        print(json.dumps(ready, indent=2))
        return

    if not ready:
        print("No ready tasks found.")
        return

    print("Ready Tasks:")
    for task in ready:
        assigned = f" (assigned: {task.get('assigned_agent')})" if task.get("assigned_agent") else ""
        print(f"  - [{task.get('id')}] {task.get('title')}{assigned}")


def task_next_command(agent: str, root_dir: str = ".") -> None:
    tasks = load_all_plan_tasks(root_dir)
    if not tasks:
        print("No tasks or plans found under .devflow/plans/.")
        return

    try:
        dag = TaskDAG(tasks, root_dir=root_dir)
    except ValueError as exc:
        print(f"Error building graph: {exc}")
        sys.exit(1)

    next_task = dag.get_next_task(agent=agent)
    if not next_task:
        print(f"No ready tasks found for agent '{agent}'.")
        return

    assigned = f" (assigned: {next_task.get('assigned_agent')})" if next_task.get("assigned_agent") else ""
    print(f"Next Task: [{next_task.get('id')}] {next_task.get('title')}{assigned}")


def task_graph_command(root_dir: str = ".") -> None:
    tasks = load_all_plan_tasks(root_dir)
    if not tasks:
        print("No tasks or plans found under .devflow/plans/.")
        return

    try:
        dag = TaskDAG(tasks, root_dir=root_dir)
    except ValueError as exc:
        print(f"Error building graph: {exc}")
        return

    print("Task Dependency Graph:")
    for task_id, task in sorted(dag.tasks.items()):
        status = task.get("status", "PENDING")
        title = task.get("title", "Unknown")
        assigned = f" (assigned: {task.get('assigned_agent')})" if task.get("assigned_agent") else ""
        deps = dag.dependencies.get(task_id, [])
        deps_str = f" [depends on: {', '.join(deps)}]" if deps else ""
        print(f"[{task_id}] {status}: {title}{assigned}{deps_str}")


def task_status_command(task_file: str) -> None:
    try:
        content = read_task_markdown(task_file)
    except FileNotFoundError as exc:
        print(f"Error: {exc}")
        sys.exit(1)

    task = parse_task_file(content)
    latest_report = latest_report_for_task(task)
    plan_status = plan_status_for_task(task)

    print(f"Task {task.get('task_id', 'unknown')} - {task.get('title', 'Unknown')}")
    print(f"status: {task.get('status', '')}")
    print(f"assigned_agent: {task.get('assigned_agent', '')}")
    print(f"owner_lock: {task.get('owner_lock', '')}")
    print(f"branch: {task.get('branch', '')}")
    print(f"touched_files: {', '.join(task.get('touched_files', []))}")
    print(f"allowed_files: {', '.join(task.get('allowed_files', []))}")
    print(f"latest_report: {latest_report}")
    print(f"plan_status: {plan_status}")

    transitions = task.get("transitions", [])
    if transitions:
        print("transitions:")
        for transition in transitions:
            print(f"  - {transition}")

    verification_lines = verification_results_from_report(latest_report)
    if verification_lines:
        print("verification_results:")
        for line in verification_lines:
            print(f"  {line}")


def task_transition_command(task_file: str, to_state: str, reason: str = "", artifact_id: str = "") -> None:
    try:
        task_id, current_status, target_status = transition_task_file(
            task_file,
            to_state=to_state,
            reason=reason,
            artifact_id=artifact_id,
        )
    except FileNotFoundError as exc:
        print(f"Error: {exc}")
        sys.exit(1)
    except ValueError as exc:
        print(f"Error: {exc}")
        sys.exit(1)

    print(f"Task {task_id} transitioned from {current_status} to {target_status}.")


def task_claim_command(
    task_file: str,
    agent: str,
    owner_lock: str,
    touched_files: list[str] | None = None,
    branch: str | None = None,
    force: bool = False,
) -> bool:
    try:
        claimed, task_id, branch_or_status = claim_task_file(
            task_file,
            agent=agent,
            owner_lock=owner_lock,
            touched_files=touched_files,
            branch=branch,
            force=force,
        )
    except FileNotFoundError as exc:
        print(f"Error: {exc}")
        sys.exit(1)

    if not claimed:
        print(f"Task {task_id} is already {branch_or_status}. Use --force to override.")
        return False

    print(f"Task {task_id} claimed by {agent} ({owner_lock}).")
    return True


def task_release_command(task_file: str) -> bool:
    try:
        task_id, next_status = release_task_file(task_file)
    except FileNotFoundError as exc:
        print(f"Error: {exc}")
        sys.exit(1)

    print(f"Task {task_id} released to {next_status}.")
    return True


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", value.strip().lower()).strip("_")
    return slug or "task"


def task_new_command(
    task_id: str,
    title: str,
    goal: str = "",
    plan: str = "",
    agent: str = "",
    risk: str = "LOW",
    allowed_files: list[str] | None = None,
    touched_files: list[str] | None = None,
    verification_commands: list[str] | None = None,
    output: str | None = None,
    force: bool = False,
) -> str:
    if not os.path.exists(".devflow"):
        print("Error: .devflow/ folder not found. Run 'devflow init' first.")
        sys.exit(1)

    os.makedirs(os.path.join(".devflow", "tasks"), exist_ok=True)
    task_path = output or os.path.join(".devflow", "tasks", f"{task_id}_{_slugify(title)}.md")
    if os.path.exists(task_path) and not force:
        raise FileExistsError(f"Task already exists: {task_path}")

    content = build_task_template(
        task_id=task_id,
        title=title,
        goal=goal,
        plan=plan,
        agent=agent,
        risk=risk,
        allowed_files=allowed_files,
        touched_files=touched_files,
        verification_commands=verification_commands,
    )
    with open(task_path, "w", encoding="utf-8") as handle:
        handle.write(content)
    print(f"Created task: {task_path}")
    return task_path
