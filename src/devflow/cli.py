import argparse
import json
import os
import re
import sys
import datetime

from devflow.artifacts import find_artifact, list_artifacts, read_artifact
from devflow.context import build_context_pack, inspect_context_pack, list_context_packs
from devflow.manager import extract_unified_diff, parse_task_file
from devflow.repo_map import refresh_repo_maps
from devflow.runner import (
    DEFAULT_TAXONOMY,
    apply_patch,
    classify_failure,
    create_checkpoint_branch,
    detect_files_from_unified_diff,
    discover_verification_commands,
    dry_run_apply,
    get_dirty_worktree_files,
    paths_outside_allowed,
    protected_paths_touched,
    retry_budget_for,
    rollback_to_checkpoint,
    run_verification,
    write_task_report,
)


def _default_config() -> dict:
    return {
        "version": "0.1.0",
        "git": {
            "require_clean_worktree": True,
            "checkpoint_strategy": "branch",
            "branch_prefix": "devflow/task-",
            "auto_commit_on_success": False,
        },
        "verification": {
            "test_command": "auto",
            "lint_command": "auto",
            "typecheck_command": "auto",
        },
        "risk": {
            "default_mode": "review",
            "auto_apply_low_risk": False,
            "require_approval_for_protected_paths": True,
            "protected_paths": [
                ".env",
                ".env.*",
                "**/.env",
                "**/.env.*",
                "**/secrets/**",
                "**/secret/**",
                "**/auth/**",
                "**/payments/**",
                "**/billing/**",
                "**/migrations/**",
                ".github/workflows/**",
                "package-lock.json",
                "pnpm-lock.yaml",
                "yarn.lock",
                "poetry.lock",
                "requirements*.txt",
                "pyproject.toml",
            ]
        },
        "failure_taxonomy": DEFAULT_TAXONOMY,
    }


def _default_constitution() -> str:
    return """# devflow Constitution (MVP)\n\n- Files and git are the source of truth.\n- Unified diffs are the only supported patch protocol for MVP.\n- Protected file changes require human approval before apply.\n- Verification should run from task commands, config commands, or auto-detection.\n- Reports are mandatory for every task run.\n- devflow run previews by default; --yes is required to apply patches.\n- devflow run must stop before mutation when the git worktree is dirty.\n- Model/provider routing is post-MVP.\n"""


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


def _write_orchestrator_templates() -> None:
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


def _load_config() -> dict:
    config_path = os.path.join(".devflow", "config.json")
    if not os.path.exists(config_path):
        return _default_config()
    with open(config_path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _replace_status(task_content: str, new_status: str) -> str:
    if re.search(r"^Status:\s*.*$", task_content, flags=re.MULTILINE):
        return re.sub(r"^Status:\s*.*$", f"Status: {new_status}", task_content, count=1, flags=re.MULTILINE)
    return task_content


def _metadata_insert_index(lines: list[str]) -> int:
    for index, line in enumerate(lines):
        if line.startswith("## "):
            return index
    return len(lines)


def _upsert_header(content: str, key: str, value: str) -> str:
    lines = content.splitlines()
    end = _metadata_insert_index(lines)
    pattern = re.compile(rf"^{re.escape(key)}:\s*.*$")
    for index in range(end):
        if pattern.match(lines[index]):
            lines[index] = f"{key}: {value}"
            return "\n".join(lines) + ("\n" if content.endswith("\n") else "")

    insert_at = 1 if lines and lines[0].startswith("# ") else end
    lines.insert(insert_at, f"{key}: {value}")
    return "\n".join(lines) + ("\n" if content.endswith("\n") else "")


def _upsert_header_list(content: str, key: str, values: list[str]) -> str:
    lines = content.splitlines()
    end = _metadata_insert_index(lines)
    key_pattern = re.compile(rf"^{re.escape(key)}:\s*.*$")
    new_block = [f"{key}:"] + [f"- {value}" for value in values]

    for index in range(end):
        if not key_pattern.match(lines[index]):
            continue
        remove_end = index + 1
        while remove_end < end and lines[remove_end].strip().startswith("- "):
            remove_end += 1
        lines[index:remove_end] = new_block
        return "\n".join(lines) + ("\n" if content.endswith("\n") else "")

    insert_at = end
    lines[insert_at:insert_at] = new_block
    return "\n".join(lines) + ("\n" if content.endswith("\n") else "")


def _read_task_markdown(task_file: str) -> str:
    if not os.path.exists(task_file):
        print(f"Error: task file does not exist: {task_file}")
        sys.exit(1)
    with open(task_file, "r", encoding="utf-8") as handle:
        return handle.read()


def _write_task_markdown(task_file: str, content: str) -> None:
    with open(task_file, "w", encoding="utf-8") as handle:
        handle.write(content)


def _default_task_branch(task: dict, agent: str) -> str:
    task_id = str(task.get("task_id", "000"))
    owner = agent.strip().replace(" ", "-")
    return f"devflow/task-{task_id}-{owner}"


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", value.strip().lower()).strip("_")
    return slug or "task"


def _list_block(values: list[str], fallback: str = "- ") -> str:
    if not values:
        return fallback
    return "\n".join(f"- {value}" for value in values)


def _build_task_template(
    task_id: str,
    title: str,
    goal: str = "",
    plan: str = "",
    agent: str = "",
    risk: str = "LOW",
    branch: str = "",
    allowed_files: list[str] | None = None,
    touched_files: list[str] | None = None,
    verification_commands: list[str] | None = None,
) -> str:
    allowed_files = allowed_files or []
    touched_files = touched_files or []
    verification_commands = verification_commands or []
    branch = branch or f"devflow/task-{task_id}-{agent}" if agent else f"devflow/task-{task_id}"

    return f"""# Task: {task_id} - {title}
Status: PENDING
Goal: {goal}
Plan: {plan}
Assigned Agent: {agent}
Owner Lock:
Risk: {risk}
Branch: {branch}
Touched Files:
{_list_block(touched_files)}

## 1. Objective

Describe the concrete outcome for this task.

## 2. Allowed Files

{_list_block(allowed_files)}

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

{_list_block(verification_commands, '- true')}

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
"""


def new_task(
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
    """Create a canonical task markdown file."""
    if not os.path.exists(".devflow"):
        print("Error: .devflow/ folder not found. Run 'devflow init' first.")
        sys.exit(1)

    os.makedirs(os.path.join(".devflow", "tasks"), exist_ok=True)
    task_path = output or os.path.join(".devflow", "tasks", f"{task_id}_{_slugify(title)}.md")
    if os.path.exists(task_path) and not force:
        raise FileExistsError(f"Task already exists: {task_path}")

    content = _build_task_template(
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


def _resolve_plan_path(plan_ref: object) -> str:
    if not isinstance(plan_ref, str) or not plan_ref.strip():
        return ""
    plan_ref = plan_ref.strip()
    if os.path.exists(plan_ref):
        return plan_ref
    return os.path.join(".devflow", "plans", plan_ref)


def _mirror_plan_status(task: dict, new_status: str) -> str:
    plan_path = _resolve_plan_path(task.get("plan"))
    if not plan_path or not os.path.exists(plan_path):
        return ""

    try:
        with open(plan_path, "r", encoding="utf-8") as handle:
            plan = json.load(handle)
        tasks = plan.get("tasks", [])
        if not isinstance(tasks, list):
            return f"Plan status mirror skipped: {plan_path} has no tasks list."

        task_id = str(task.get("task_id", ""))
        for item in tasks:
            if isinstance(item, dict) and str(item.get("id", "")) == task_id:
                item["status"] = new_status
                with open(plan_path, "w", encoding="utf-8") as handle:
                    json.dump(plan, handle, indent=2)
                    handle.write("\n")
                return ""
        return f"Plan status mirror skipped: task {task_id} not found in {plan_path}."
    except Exception as exc:
        return f"Plan status mirror failed: {exc}"


def _write_task_status(task_file: str, new_status: str, task: dict, report_payload: dict) -> None:
    with open(task_file, "r", encoding="utf-8") as handle:
        latest_task = handle.read()
    previous_status = report_payload.get("_current_status") or parse_task_file(latest_task).get("status", "")
    with open(task_file, "w", encoding="utf-8") as handle:
        handle.write(_replace_status(latest_task, new_status))

    if previous_status and previous_status != new_status:
        transitions = report_payload.setdefault("status_transitions", [])
        if isinstance(transitions, list):
            transitions.append(f"{previous_status} -> {new_status}")
    report_payload["_current_status"] = new_status

    warning = _mirror_plan_status(task, new_status)
    if warning:
        warnings = report_payload.setdefault("warnings", [])
        if isinstance(warnings, list):
            warnings.append(warning)


def claim_task(
    task_file: str,
    agent: str,
    owner_lock: str,
    touched_files: list[str] | None = None,
    branch: str | None = None,
    force: bool = False,
) -> bool:
    """Claim a task for one peer orchestrator."""
    content = _read_task_markdown(task_file)
    task = parse_task_file(content)
    status = str(task.get("status", "PENDING"))
    if status in {"CLAIMED", "RUNNING"} and not force:
        print(f"Task {task.get('task_id', 'unknown')} is already {status}. Use --force to override.")
        return False

    branch_name = branch or _default_task_branch(task, agent)
    updated = _replace_status(content, "CLAIMED")
    updated = _upsert_header(updated, "Assigned Agent", agent)
    updated = _upsert_header(updated, "Owner Lock", owner_lock)
    updated = _upsert_header(updated, "Branch", branch_name)
    if touched_files is not None:
        updated = _upsert_header_list(updated, "Touched Files", touched_files)

    _write_task_markdown(task_file, updated)
    print(f"Task {task.get('task_id', 'unknown')} claimed by {agent} ({owner_lock}).")
    return True


def release_task(task_file: str) -> bool:
    """Release an owned task back to the shared queue."""
    content = _read_task_markdown(task_file)
    task = parse_task_file(content)
    current_status = str(task.get("status", "PENDING"))
    next_status = "BLOCKED" if current_status == "BLOCKED" else "PENDING"

    updated = _replace_status(content, next_status)
    updated = _upsert_header(updated, "Assigned Agent", "")
    updated = _upsert_header(updated, "Owner Lock", "")
    updated = _upsert_header(updated, "Branch", "")

    _write_task_markdown(task_file, updated)
    print(f"Task {task.get('task_id', 'unknown')} released to {next_status}.")
    return True


def _plan_status_for_task(task: dict) -> str:
    plan_path = _resolve_plan_path(task.get("plan"))
    if not plan_path or not os.path.exists(plan_path):
        return ""
    try:
        with open(plan_path, "r", encoding="utf-8") as handle:
            plan = json.load(handle)
    except Exception:
        return ""

    task_id = str(task.get("task_id", ""))
    for item in plan.get("tasks", []):
        if isinstance(item, dict) and str(item.get("id", "")) == task_id:
            return str(item.get("status", ""))
    return ""


def status_task(task_file: str) -> None:
    """Print task ownership and coordination status."""
    content = _read_task_markdown(task_file)
    task = parse_task_file(content)
    report_path = os.path.join(".devflow", "reports", f"{task.get('task_id', 'unknown')}.report.md")
    latest_report = report_path if os.path.exists(report_path) else ""
    plan_status = _plan_status_for_task(task)

    print(f"Task {task.get('task_id', 'unknown')} - {task.get('title', 'Unknown')}")
    print(f"status: {task.get('status', '')}")
    print(f"assigned_agent: {task.get('assigned_agent', '')}")
    print(f"owner_lock: {task.get('owner_lock', '')}")
    print(f"branch: {task.get('branch', '')}")
    print(f"touched_files: {', '.join(task.get('touched_files', []))}")
    print(f"allowed_files: {', '.join(task.get('allowed_files', []))}")
    print(f"latest_report: {latest_report}")
    print(f"plan_status: {plan_status}")

    # Display TDD transitions if any exist
    transitions = task.get("transitions", [])
    if transitions:
        print("transitions:")
        for trans in transitions:
            print(f"  - {trans}")

    # Extract and display verification step execution results from report if available
    if latest_report and os.path.exists(latest_report):
        try:
            with open(latest_report, "r", encoding="utf-8") as handle:
                report_content = handle.read()
            lines = report_content.splitlines()
            in_verification = False
            verif_lines = []
            for line in lines:
                if line.startswith("## Verification Commands"):
                    in_verification = True
                    continue
                if in_verification:
                    if line.startswith("## "):
                        break
                    if line.strip():
                        verif_lines.append(line.strip())
            if verif_lines:
                print("verification_results:")
                for vl in verif_lines:
                    print(f"  {vl}")
        except Exception:
            pass


def transition_task(task_file: str, to_state: str, reason: str = "", artifact_id: str = "") -> None:
    """Transition a task between canonical TDD states with validation."""
    content = _read_task_markdown(task_file)
    task = parse_task_file(content)
    current_status = str(task.get("status", "PENDING")).upper()
    target_status = to_state.upper()

    from devflow.states import validate_transition
    if not validate_transition(current_status, target_status):
        print(f"Error: Transition from '{current_status}' to '{target_status}' is invalid.")
        sys.exit(1)

    # Construct the transition entry
    timestamp = datetime.datetime.now().replace(microsecond=0).isoformat()
    if reason and artifact_id:
        trans_str = f"{current_status} -> {target_status}: {reason} (artifact: {artifact_id}) at {timestamp}"
    elif reason:
        trans_str = f"{current_status} -> {target_status}: {reason} at {timestamp}"
    elif artifact_id:
        trans_str = f"{current_status} -> {target_status}: (artifact: {artifact_id}) at {timestamp}"
    else:
        trans_str = f"{current_status} -> {target_status} at {timestamp}"

    current_transitions = task.get("transitions", [])
    current_transitions.append(trans_str)

    updated = _replace_status(content, target_status)
    updated = _upsert_header_list(updated, "Transitions", current_transitions)

    _write_task_markdown(task_file, updated)
    print(f"Task {task.get('task_id', 'unknown')} transitioned from {current_status} to {target_status}.")


def _load_all_plan_tasks(root_dir: str = ".") -> list[dict]:
    plans_dir = os.path.join(root_dir, ".devflow", "plans")
    if not os.path.isdir(plans_dir):
        return []
    all_tasks = []
    for filename in os.listdir(plans_dir):
        if filename.endswith(".plan.json"):
            path = os.path.join(plans_dir, filename)
            try:
                with open(path, "r", encoding="utf-8") as handle:
                    plan_data = json.load(handle)
                tasks = plan_data.get("tasks", [])
                for t in tasks:
                    if isinstance(t, dict) and "id" in t:
                        all_tasks.append(t)
            except Exception:
                pass
    return all_tasks


def task_ready(json_output: bool = False, root_dir: str = ".") -> None:
    tasks = _load_all_plan_tasks(root_dir)
    if not tasks:
        if json_output:
            print("[]")
        else:
            print("No tasks or plans found under .devflow/plans/.")
        return

    from devflow.dag import TaskDAG
    try:
        dag = TaskDAG(tasks, root_dir=root_dir)
    except ValueError as e:
        print(f"Error building graph: {e}")
        sys.exit(1)

    ready = dag.get_ready_tasks()
    if json_output:
        print(json.dumps(ready, indent=2))
    else:
        if not ready:
            print("No ready tasks found.")
        else:
            print("Ready Tasks:")
            for t in ready:
                assigned = f" (assigned: {t.get('assigned_agent')})" if t.get('assigned_agent') else ""
                print(f"  - [{t.get('id')}] {t.get('title')}{assigned}")


def task_next(agent: str, root_dir: str = ".") -> None:
    tasks = _load_all_plan_tasks(root_dir)
    if not tasks:
        print("No tasks or plans found under .devflow/plans/.")
        return

    from devflow.dag import TaskDAG
    try:
        dag = TaskDAG(tasks, root_dir=root_dir)
    except ValueError as e:
        print(f"Error building graph: {e}")
        sys.exit(1)

    next_task = dag.get_next_task(agent=agent)
    if not next_task:
        print(f"No ready tasks found for agent '{agent}'.")
    else:
        assigned = f" (assigned: {next_task.get('assigned_agent')})" if next_task.get('assigned_agent') else ""
        print(f"Next Task: [{next_task.get('id')}] {next_task.get('title')}{assigned}")


def task_graph(root_dir: str = ".") -> None:
    tasks = _load_all_plan_tasks(root_dir)
    if not tasks:
        print("No tasks or plans found under .devflow/plans/.")
        return

    from devflow.dag import TaskDAG
    try:
        dag = TaskDAG(tasks, root_dir=root_dir)
    except ValueError as e:
        print(f"Error building graph: {e}")
        return

    print("Task Dependency Graph:")
    for task_id, task in sorted(dag.tasks.items()):
        status = task.get("status", "PENDING")
        title = task.get("title", "Unknown")
        assigned = f" (assigned: {task.get('assigned_agent')})" if task.get('assigned_agent') else ""
        deps = dag.dependencies.get(task_id, [])
        deps_str = f" [depends on: {', '.join(deps)}]" if deps else ""
        print(f"[{task_id}] {status}: {title}{assigned}{deps_str}")


def impact_command(task_file: str) -> None:
    from devflow.impact import analyze_impact
    try:
        report = analyze_impact(task_file, os.getcwd())
    except FileNotFoundError as e:
        print(f"Error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error analyzing impact: {e}")
        sys.exit(1)

    print(f"Impact Analysis Report for Task {report.get('task_id')} - {report.get('title')}")
    print(f"======================================================================")
    print(f"Risk Level: {report.get('risk_level')} (score: {report.get('risk_score')})")
    print(f"Allowed Files:")
    for f in report.get("allowed_files", []):
        print(f"  - {f}")
    if report.get("touched_files"):
        print(f"Touched Files:")
        for f in report.get("touched_files", []):
            print(f"  - {f}")

    print(f"\nWorkspace Import Usages:")
    usages = report.get("public_interface_usages", [])
    if not usages:
        print("  None detected (no external files import these modules).")
    else:
        for u in usages:
            print(f"  - {u}")

    print(f"\nGit History Co-mutations (frequently changed together):")
    co = report.get("co_mutations", [])
    if not co:
        print("  None detected.")
    else:
        for c in co:
            print(f"  - {c}")

    print(f"\nVerification Targets (relevant tests to run):")
    tests = report.get("verification_targets", [])
    if not tests:
        print("  None detected.")
    else:
        for t in tests:
            print(f"  - {t}")

    if report.get("suggests_split"):
        print(f"\nWARNING: Task Split Recommended!")
        print(f"Reason: {report.get('split_reason')}")



def init_workspace():
    """Initialize the canonical .devflow protocol tree."""
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
    ]
    os.makedirs(".devflow", exist_ok=True)
    for folder in folders:
        os.makedirs(os.path.join(".devflow", folder), exist_ok=True)

    config_path = os.path.join(".devflow", "config.json")
    with open(config_path, "w", encoding="utf-8") as handle:
        json.dump(_default_config(), handle, indent=2)

    constitution_path = os.path.join(".devflow", "constitution.md")
    with open(constitution_path, "w", encoding="utf-8") as handle:
        handle.write(_default_constitution())

    _write_orchestrator_templates()

    print("Initialized empty devflow workspace in .devflow/")

def status_workspace():
    """Print a summary of goal/plan/task state from .devflow."""
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
    print(f"- tasks: {len([t for t in tasks if t.endswith('.md')])}")
    for key in ("PENDING", "CLAIMED", "PREVIEWED", "RUNNING", "COMPLETED", "FAILED", "BLOCKED"):
        print(f"- {key.lower()}: {statuses[key]}")


def artifact_list(task_id: str) -> None:
    """Print artifact metadata for one task."""
    records = list_artifacts(task_id)
    if not records:
        print(f"No artifacts found for task {task_id}.")
        return

    for record in records:
        metadata = record.metadata
        print(
            f"{record.sequence:03d} {metadata.get('artifact_id', '')} "
            f"{metadata.get('artifact_type', '')} "
            f"role={metadata.get('role', '')} "
            f"created_at={metadata.get('created_at', '')} "
            f"apply={metadata.get('apply_status', '')} "
            f"verify={metadata.get('verification_status', '')}"
        )


def artifact_inspect(identifier: str) -> None:
    """Print metadata and body location for one artifact."""
    record = find_artifact(identifier)
    metadata, _ = read_artifact(record.metadata_path)
    print(json.dumps(metadata, indent=2, sort_keys=True))


def context_refresh() -> None:
    """Refresh deterministic repository maps under .devflow/context."""
    paths = refresh_repo_maps()
    print("repo maps refreshed")
    for name in ("short", "symbols", "deps"):
        print(f"{name}: {paths[name]}")


def context_build(task_file: str, role: str, budget: int | None = None) -> None:
    """Build and store a context pack artifact for one task and role."""
    record = build_context_pack(task_file, role=role, token_budget=budget)
    summary = inspect_context_pack(record.artifact_id)
    print(f"context_pack_id: {summary['context_pack_id']}")
    print(f"artifact_id: {record.artifact_id}")
    print(f"body_path: {record.body_path}")
    print(f"token_estimate: {summary['token_estimate']}/{summary['token_budget']}")


def context_inspect(identifier: str) -> None:
    """Print a context pack summary by artifact id or path."""
    print(json.dumps(inspect_context_pack(identifier), indent=2, sort_keys=True))


def context_list(task_id: str) -> None:
    """List context-pack artifacts for one task."""
    records = list_context_packs(task_id)
    if not records:
        print(f"No context packs found for task {task_id}.")
        return
    for record in records:
        summary = inspect_context_pack(record.artifact_id)
        print(
            f"{record.sequence:03d} {record.artifact_id} "
            f"{summary['context_pack_id']} role={summary['role']} "
            f"tokens={summary['token_estimate']}/{summary['token_budget']}"
        )


def run_task(task_file: str, yes: bool = False):
    """Run a single canonical task file with unified-diff safe-edit workflow."""
    if not os.path.exists(".devflow"):
        print("Error: .devflow/ folder not found. Run 'devflow init' first.")
        sys.exit(1)

    if not os.path.exists(task_file):
        print(f"Error: task file does not exist: {task_file}")
        sys.exit(1)

    with open(task_file, "r", encoding="utf-8") as handle:
        raw_markdown = handle.read()

    config = _load_config()
    task = parse_task_file(raw_markdown)
    diff_text = extract_unified_diff(raw_markdown)
    if not diff_text.strip():
        print("Error: no unified diff block found in task file.")
        sys.exit(1)

    files_changed = detect_files_from_unified_diff(diff_text)
    protected_patterns = config.get("risk", {}).get("protected_paths", [])
    protected = protected_paths_touched(files_changed, protected_patterns)

    clean, dirty_files, dirty_error = get_dirty_worktree_files(os.getcwd())
    if not clean:
        print("Task blocked: git worktree is dirty. Commit or stash changes before running devflow.")
        if dirty_error:
            print(f"- git status error: {dirty_error}")
        for path in dirty_files:
            print(f"- {path}")
        return

    report_payload = {
        "task_id": task.get("task_id", "unknown"),
        "status": "FAILED",
        "assigned_agent": task.get("assigned_agent", ""),
        "owner_lock": task.get("owner_lock", ""),
        "touched_files": task.get("touched_files", []),
        "checkpoint_branch": "",
        "base_branch": "",
        "files_changed": files_changed,
        "protected_files": protected,
        "patch_result": "not_applied",
        "verification": [],
        "failure_classification": "",
        "rollback_status": "not_started",
        "final_outcome": "",
        "dirty_worktree_decision": "clean",
        "protected_paths_decision": "none" if not protected else f"blocked: {', '.join(protected)}",
        "allowed_files_decision": "not_checked",
    }

    if protected:
        report_payload["status"] = "BLOCKED"
        report_payload["failure_classification"] = "PROTECTED_FILE_TOUCHED"
        report_payload["final_outcome"] = "Stopped before patch apply. Human approval required."
        _write_task_status(task_file, "BLOCKED", task, report_payload)
        report_file = os.path.join(".devflow", "reports", f"{task.get('task_id', 'unknown')}.report.md")
        write_task_report(report_file, report_payload)
        print("Task blocked: protected paths detected in patch.")
        return

    allowed = task.get("allowed_files", [])
    if isinstance(allowed, list) and allowed:
        outside_allowed = paths_outside_allowed(files_changed, allowed)
        if outside_allowed:
            report_payload["allowed_files_decision"] = f"blocked: {', '.join(outside_allowed)}"
            report_payload["failure_classification"] = "UNKNOWN_FAILURE"
            report_payload["final_outcome"] = "Patch modifies files outside Allowed Files."
            _write_task_status(task_file, "FAILED", task, report_payload)
            report_file = os.path.join(".devflow", "reports", f"{task.get('task_id', 'unknown')}.report.md")
            write_task_report(report_file, report_payload)
            print("Task failed: patch modifies files outside Allowed Files.")
            return
        report_payload["allowed_files_decision"] = "all changed files allowed"
    else:
        report_payload["allowed_files_decision"] = "not configured"

    ok, base_branch, checkpoint = create_checkpoint_branch(
        cwd=os.getcwd(),
        task_id=str(task.get("task_id", "000")),
        branch_prefix=config.get("git", {}).get("branch_prefix", "devflow/task-"),
    )
    if not ok:
        print(f"Error creating checkpoint branch: {checkpoint}")
        sys.exit(1)

    report_payload["base_branch"] = base_branch
    report_payload["checkpoint_branch"] = checkpoint

    _write_task_status(task_file, "RUNNING", task, report_payload)

    applied = False
    patch_ok, patch_output = dry_run_apply(diff_text, os.getcwd())
    if not patch_ok:
        classification = classify_failure("patch", patch_output)
        report_payload["failure_classification"] = classification
        retries = retry_budget_for(classification, config.get("failure_taxonomy", DEFAULT_TAXONOMY))
        if retries > 0:
            patch_ok, patch_output = dry_run_apply(diff_text, os.getcwd())

    if not patch_ok:
        report_payload["patch_result"] = f"dry_run_failed: {patch_output}".strip()
        report_payload["status"] = "FAILED"
        report_payload["final_outcome"] = "Patch dry-run failed."
    else:
        if not yes:
            report_payload["patch_result"] = "dry_run_passed"
            report_payload["status"] = "PREVIEWED"
            report_payload["final_outcome"] = "Patch validated and previewed. Re-run with --yes to apply."
            final_status = report_payload["status"]
            _write_task_status(task_file, str(final_status), task, report_payload)
            report_file = os.path.join(".devflow", "reports", f"{task.get('task_id', 'unknown')}.report.md")
            write_task_report(report_file, report_payload)
            print(f"Task {task.get('task_id', 'unknown')} previewed. Re-run with --yes to apply.")
            return

        apply_ok, apply_output = apply_patch(diff_text, os.getcwd())
        report_payload["patch_result"] = "applied" if apply_ok else f"apply_failed: {apply_output}".strip()
        if apply_ok:
            applied = True
            commands = task.get("verification_commands") or discover_verification_commands(config, os.getcwd())
            verify_ok, verify_results = run_verification(commands, os.getcwd())
            report_payload["verification"] = verify_results
            if verify_ok:
                report_payload["status"] = "COMPLETED"
                report_payload["final_outcome"] = "Patch applied and verification passed."
            else:
                combined_output = "\n".join(
                    f"{item.get('stdout', '')}\n{item.get('stderr', '')}" for item in verify_results
                )
                failure = classify_failure("verification", combined_output)
                report_payload["failure_classification"] = failure
                retries = retry_budget_for(failure, config.get("failure_taxonomy", DEFAULT_TAXONOMY))
                if retries > 0:
                    verify_ok_retry, verify_results_retry = run_verification(commands, os.getcwd())
                    report_payload["verification"] = verify_results_retry
                    if verify_ok_retry:
                        report_payload["status"] = "COMPLETED"
                        report_payload["final_outcome"] = "Verification succeeded on retry."
                    else:
                        rolled_back, rollback_msg = rollback_to_checkpoint(os.getcwd(), files_changed)
                        report_payload["rollback_status"] = rollback_msg if rolled_back else f"rollback_failed: {rollback_msg}"
                        report_payload["status"] = "FAILED"
                        report_payload["final_outcome"] = "Verification failed after retry; checkpoint rollback performed."
                else:
                    rolled_back, rollback_msg = rollback_to_checkpoint(os.getcwd(), files_changed)
                    report_payload["rollback_status"] = rollback_msg if rolled_back else f"rollback_failed: {rollback_msg}"
                    report_payload["status"] = "FAILED"
                    report_payload["final_outcome"] = "Verification failed; checkpoint rollback performed."
        else:
            report_payload["failure_classification"] = classify_failure("patch", apply_output)
            report_payload["status"] = "FAILED"
            report_payload["final_outcome"] = "Patch apply failed."

    final_status = report_payload["status"]
    _write_task_status(task_file, str(final_status), task, report_payload)

    report_file = os.path.join(".devflow", "reports", f"{task.get('task_id', 'unknown')}.report.md")
    write_task_report(report_file, report_payload)

    if applied and final_status != "COMPLETED" and report_payload.get("rollback_status") == "not_started":
        rolled_back, rollback_msg = rollback_to_checkpoint(os.getcwd(), files_changed)
        report_payload["rollback_status"] = rollback_msg if rolled_back else f"rollback_failed: {rollback_msg}"

    print(f"Task {task.get('task_id', 'unknown')} finished with status: {final_status}")

def main():
    parser = argparse.ArgumentParser(description="devflow - Safe unified-diff MVP runner")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("init", help="Initialize a new devflow workspace")
    subparsers.add_parser("status", help="Show goal, plan, and task state")

    task_parser = subparsers.add_parser("task", help="Manage task ownership and status")
    task_subparsers = task_parser.add_subparsers(dest="task_command")

    new_parser = task_subparsers.add_parser("new", help="Create a canonical task markdown file")
    new_parser.add_argument("task_id", type=str, help="Task id, e.g. 001")
    new_parser.add_argument("title", type=str, help="Task title")
    new_parser.add_argument("--goal", default="", help="Goal id/reference")
    new_parser.add_argument("--plan", default="", help="Plan JSON filename or path")
    new_parser.add_argument("--agent", default="", help="Initial assigned orchestrator")
    new_parser.add_argument("--risk", default="LOW", help="Risk level")
    new_parser.add_argument("--allowed", action="append", default=[], help="Allowed file path/glob; may be repeated")
    new_parser.add_argument("--touch", action="append", default=[], help="Expected touched file/glob; may be repeated")
    new_parser.add_argument("--verify", action="append", default=[], help="Verification command; may be repeated")
    new_parser.add_argument("--output", help="Output task path")
    new_parser.add_argument("--force", action="store_true", help="Overwrite existing task file")

    claim_parser = task_subparsers.add_parser("claim", help="Claim a task for an orchestrator")
    claim_parser.add_argument("task_file", type=str, help="Path to canonical task markdown file")
    claim_parser.add_argument("--agent", required=True, help="Owning orchestrator: codex, vscode, or antigravity")
    claim_parser.add_argument("--lock", required=True, help="Session/team lock identifier")
    claim_parser.add_argument("--branch", help="Branch name to write into the task header")
    claim_parser.add_argument("--touch", action="append", default=[], help="Expected touched file or glob; may be repeated")
    claim_parser.add_argument("--force", action="store_true", help="Override an existing CLAIMED/RUNNING task")

    release_parser = task_subparsers.add_parser("release", help="Release a claimed task")
    release_parser.add_argument("task_file", type=str, help="Path to canonical task markdown file")

    task_status_parser = task_subparsers.add_parser("status", help="Show one task's coordination status")
    task_status_parser.add_argument("task_file", type=str, help="Path to canonical task markdown file")

    transition_parser = task_subparsers.add_parser("transition", help="Transition a task between TDD states")
    transition_parser.add_argument("task_file", type=str, help="Path to canonical task markdown file")
    transition_parser.add_argument("--to", required=True, help="Target state, e.g. RED, GREEN, REFACTOR, REPORT")
    transition_parser.add_argument("--reason", default="", help="Reason for the transition")
    transition_parser.add_argument("--artifact", default="", help="Artifact ID associated with this transition")

    ready_parser = task_subparsers.add_parser("ready", help="List unblocked dependency-ready tasks")
    ready_parser.add_argument("--json", action="store_true", help="Format output as JSON list")

    next_parser = task_subparsers.add_parser("next", help="Get next task to execute for an agent")
    next_parser.add_argument("--agent", required=True, help="Agent name")

    graph_parser = task_subparsers.add_parser("graph", help="Show the hierarchical task dependency graph")

    run_parser = subparsers.add_parser("run", help="Run a single task markdown file")
    run_parser.add_argument("task_file", type=str, help="Path to canonical task markdown file")
    run_parser.add_argument("--yes", action="store_true", help="Apply the patch after validation")

    impact_parser = subparsers.add_parser("impact", help="Analyze task allowed/touched files change impact")
    impact_parser.add_argument("task_file", type=str, help="Path to canonical task markdown file")

    artifact_parser = subparsers.add_parser("artifact", help="Inspect and list task artifacts")
    artifact_subparsers = artifact_parser.add_subparsers(dest="artifact_command")

    artifact_list_parser = artifact_subparsers.add_parser("list", help="List artifacts for a task")
    artifact_list_parser.add_argument("task_id", type=str, help="Task id, e.g. T-042")

    artifact_inspect_parser = artifact_subparsers.add_parser("inspect", help="Inspect one artifact")
    artifact_inspect_parser.add_argument("identifier", type=str, help="Artifact id, metadata path, or body path")

    context_parser = subparsers.add_parser("context", help="Build and inspect bounded context packs")
    context_subparsers = context_parser.add_subparsers(dest="context_command")

    context_subparsers.add_parser("refresh", help="Refresh repository maps under .devflow/context")

    context_build_parser = context_subparsers.add_parser("build", help="Build a context pack artifact")
    context_build_parser.add_argument("task_file", type=str, help="Path to canonical task markdown file")
    context_build_parser.add_argument("--role", required=True, help="Worker role, e.g. reviewer or implementer")
    context_build_parser.add_argument("--budget", type=int, help="Token budget override")

    context_inspect_parser = context_subparsers.add_parser("inspect", help="Inspect a context pack")
    context_inspect_parser.add_argument("identifier", type=str, help="Context artifact id, metadata path, or body path")

    context_list_parser = context_subparsers.add_parser("list", help="List context packs for a task")
    context_list_parser.add_argument("task_id", type=str, help="Task id, e.g. T-042")

    agent_parser = subparsers.add_parser("agent", help="Stateless model agent commands")
    agent_subparsers = agent_parser.add_subparsers(dest="agent_command")

    agent_review_parser = agent_subparsers.add_parser("review", help="Run stateless code review agent")
    agent_review_parser.add_argument("task_file", type=str, help="Path to task file")
    agent_review_parser.add_argument("--profile", default="reviewer", help="Agent profile to use")

    agent_implement_parser = agent_subparsers.add_parser("implement", help="Run stateless code implementer agent")
    agent_implement_parser.add_argument("task_file", type=str, help="Path to task file")
    agent_implement_parser.add_argument("--profile", default="implementer", help="Agent profile to use")
    agent_implement_parser.add_argument("--emit-diff", action="store_true", help="Emit proposed diff immediately after execution")

    agent_repair_parser = agent_subparsers.add_parser("repair", help="Run automated test-driven repair loop agent")
    agent_repair_parser.add_argument("task_file", type=str, help="Path to task file")
    agent_repair_parser.add_argument("--profile", default="repair", help="Agent profile to use")
    agent_repair_parser.add_argument("--max-loops", type=int, default=3, help="Maximum repair loop limit")



    guard_parser = subparsers.add_parser("guard", help="Deterministic guard commands")
    guard_subparsers = guard_parser.add_subparsers(dest="guard_command")

    guard_scan_diff_parser = guard_subparsers.add_parser("scan-diff", help="Deterministic static hazard scan of a diff")
    guard_scan_diff_parser.add_argument("identifier", type=str, help="Artifact ID, file path, or sequence pattern")

    args = parser.parse_args()

    if args.command == "init":
        init_workspace()
    elif args.command == "status":
        status_workspace()
    elif args.command == "task":
        if args.task_command == "new":
            try:
                new_task(
                    args.task_id,
                    args.title,
                    goal=args.goal,
                    plan=args.plan,
                    agent=args.agent,
                    risk=args.risk,
                    allowed_files=args.allowed,
                    touched_files=args.touch,
                    verification_commands=args.verify,
                    output=args.output,
                    force=args.force,
                )
            except FileExistsError as exc:
                print(f"Error: {exc}")
                sys.exit(1)
        elif args.task_command == "claim":
            claim_task(
                args.task_file,
                agent=args.agent,
                owner_lock=args.lock,
                touched_files=args.touch or None,
                branch=args.branch,
                force=args.force,
            )
        elif args.task_command == "release":
            release_task(args.task_file)
        elif args.task_command == "status":
            status_task(args.task_file)
        elif args.task_command == "transition":
            transition_task(
                args.task_file,
                to_state=args.to,
                reason=args.reason,
                artifact_id=args.artifact
            )
        elif args.task_command == "ready":
            task_ready(json_output=args.json)
        elif args.task_command == "next":
            task_next(agent=args.agent)
        elif args.task_command == "graph":
            task_graph()
        else:
            task_parser.print_help()
    elif args.command == "run":
        run_task(args.task_file, yes=args.yes)
    elif args.command == "impact":
        impact_command(args.task_file)
    elif args.command == "artifact":
        if args.artifact_command == "list":
            artifact_list(args.task_id)
        elif args.artifact_command == "inspect":
            artifact_inspect(args.identifier)
        else:
            artifact_parser.print_help()
    elif args.command == "context":
        if args.context_command == "refresh":
            context_refresh()
        elif args.context_command == "build":
            context_build(args.task_file, role=args.role, budget=args.budget)
        elif args.context_command == "inspect":
            context_inspect(args.identifier)
        elif args.context_command == "list":
            context_list(args.task_id)
        else:
            context_parser.print_help()
    elif args.command == "agent":
        if args.agent_command == "review":
            from devflow.agents.runner import run_review_agent
            record = run_review_agent(args.task_file, profile_name=args.profile)
            print(f"Agent review completed. Artifact created: {record.artifact_id}")
            print(f"Path: {record.body_path}")
        elif args.agent_command == "implement":
            from devflow.agents.runner import run_implement_agent
            record = run_implement_agent(args.task_file, profile_name=args.profile)
            print(f"Agent implementation completed. Artifact created: {record.artifact_id}")
            print(f"Path: {record.body_path}")
            if args.emit_diff:
                # Read artifact and print the diff
                from devflow.artifacts import read_artifact
                _, body = read_artifact(record.body_path)
                try:
                    diff_data = json.loads(body)
                    print("\n--- PROPOSED DIFF ---")
                    print(diff_data.get("diff", ""))
                    print("---------------------")
                except Exception:
                    pass
        elif args.agent_command == "repair":
            from devflow.agents.runner import run_repair_agent
            record = run_repair_agent(args.task_file, max_loops=args.max_loops, profile_name=args.profile)
            print(f"Agent repair completed. Artifact created: {record.artifact_id}")
            print(f"Path: {record.body_path}")
        else:
            agent_parser.print_help()

    elif args.command == "guard":
        if args.guard_command == "scan-diff":
            from devflow.safety import scan_diff_for_hazards
            from devflow.artifacts import find_artifact, read_artifact
            
            diff_text = ""
            try:
                # First try finding as an artifact
                record = find_artifact(args.identifier)
                _, body = read_artifact(record.metadata_path)
                try:
                    data = json.loads(body)
                    diff_text = data.get("diff", "")
                except Exception:
                    diff_text = body
            except Exception:
                # Fall back to checking if it's a file
                if os.path.exists(args.identifier):
                    with open(args.identifier, "r", encoding="utf-8") as f:
                        content = f.read()
                    try:
                        data = json.loads(content)
                        diff_text = data.get("diff", "")
                    except Exception:
                        diff_text = content
                else:
                    print(f"Error: could not resolve identifier as an artifact or file path: {args.identifier}")
                    sys.exit(1)
            
            is_clean, findings = scan_diff_for_hazards(diff_text)
            if not is_clean:
                print("Adversarial hazards detected in proposed diff:")
                for finding in findings:
                    print(f"- {finding}")
                sys.exit(1)
            else:
                print("Safety scan completed: no adversarial hazards detected.")
                sys.exit(0)
        else:
            guard_parser.print_help()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
