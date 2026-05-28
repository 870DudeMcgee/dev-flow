from __future__ import annotations

import json
from pathlib import Path
import os
import time

from devflow.control_room.service import list_tasks


def render_dashboard(repo_root: Path | None = None) -> str:
    root = (repo_root or Path.cwd()).resolve()
    tasks = list_tasks(root)
    lines = [
        "Dev-Flow Control Room",
        f"root: {root}",
        "",
        f"{'Task':<10} {'Status':<20} {'Verify':<12} {'Worker':<8} Latest",
        "-" * 82,
    ]
    if not tasks:
        lines.append("No tasks found.")
    for task in tasks:
        # Try to load summary.json
        summary_data = {}
        summary_path = root / ".devflow" / "tasks" / task.id / "summary.json"
        if summary_path.exists():
            try:
                summary_data = json.loads(summary_path.read_text(encoding="utf-8"))
            except Exception:
                pass

        latest = task.latest_log_line or task.last_event or ""

        lines.append(f"{task.id:<10} {task.status:<20} {task.verification_status:<12} {task.worker:<8} {latest}")
        lines.append(f"  workspace: {task.workspace}")
        if task.log_path:
            lines.append(f"  log: {task.log_path}")
        if task.result_path:
            lines.append(f"  result: {task.result_path}")

        if task.verification_exit_code is not None:
            lines.append(f"  verification_exit_code: {task.verification_exit_code}")
        if task.verification_log_path:
            lines.append(f"  verification_log: {task.verification_log_path}")

        merge_ready = None
        task_path = root / ".devflow" / "tasks" / task.id
        mr_json = task_path / "merge-readiness.json"
        if mr_json.exists():
            try:
                mr_data = json.loads(mr_json.read_text(encoding="utf-8"))
                merge_ready = "yes" if mr_data.get("ready") else "no"
            except Exception:
                pass
        elif _summary_matches_task(summary_data, task):
            merge_ready = "yes" if summary_data.get("merge_ready") else "no"
        if merge_ready is not None:
            lines.append(f"  merge_ready: {merge_ready}")
    return "\n".join(lines) + "\n"


def _summary_matches_task(summary_data: dict, task) -> bool:
    if not summary_data:
        return False
    return (
        summary_data.get("task_id") == task.id
        and summary_data.get("status") == task.status
        and summary_data.get("latest_verification_status") == task.verification_status
        and summary_data.get("latest_verification_exit_code") == task.verification_exit_code
        and summary_data.get("latest_verification_log_path") == task.verification_log_path
    )


def run_dashboard(refresh_seconds: int = 0) -> None:
    while True:
        if refresh_seconds:
            os.system("clear")
        print(render_dashboard(Path.cwd()), end="")
        if not refresh_seconds:
            return
        time.sleep(refresh_seconds)
