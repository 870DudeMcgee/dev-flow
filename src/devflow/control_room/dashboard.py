from __future__ import annotations

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
        latest = task.latest_log_line or task.last_event or ""
        lines.append(f"{task.id:<10} {task.status:<20} {task.verification_status:<12} {task.worker:<8} {latest}")
        lines.append(f"  workspace: {task.workspace}")
        if task.log_path:
            lines.append(f"  log: {task.log_path}")
        if task.result_path:
            lines.append(f"  result: {task.result_path}")
    return "\n".join(lines) + "\n"


def run_dashboard(refresh_seconds: int = 0) -> None:
    while True:
        if refresh_seconds:
            os.system("clear")
        print(render_dashboard(Path.cwd()), end="")
        if not refresh_seconds:
            return
        time.sleep(refresh_seconds)
