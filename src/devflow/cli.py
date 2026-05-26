import argparse
import json
import os
import re
import sys

from devflow.manager import extract_unified_diff, parse_task_file
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
    with open(task_file, "w", encoding="utf-8") as handle:
        handle.write(_replace_status(latest_task, new_status))

    warning = _mirror_plan_status(task, new_status)
    if warning:
        warnings = report_payload.setdefault("warnings", [])
        if isinstance(warnings, list):
            warnings.append(warning)


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
            report_payload["failure_classification"] = "UNKNOWN_FAILURE"
            report_payload["final_outcome"] = "Patch modifies files outside Allowed Files."
            _write_task_status(task_file, "FAILED", task, report_payload)
            report_file = os.path.join(".devflow", "reports", f"{task.get('task_id', 'unknown')}.report.md")
            write_task_report(report_file, report_payload)
            print("Task failed: patch modifies files outside Allowed Files.")
            return

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
    run_parser = subparsers.add_parser("run", help="Run a single task markdown file")
    run_parser.add_argument("task_file", type=str, help="Path to canonical task markdown file")
    run_parser.add_argument("--yes", action="store_true", help="Apply the patch after validation")

    args = parser.parse_args()

    if args.command == "init":
        init_workspace()
    elif args.command == "status":
        status_workspace()
    elif args.command == "run":
        run_task(args.task_file, yes=args.yes)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
