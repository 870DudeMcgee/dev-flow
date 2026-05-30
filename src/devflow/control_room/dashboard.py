from __future__ import annotations

from pathlib import Path
import os
import time

from devflow.control_room.status_projection import list_task_status_projections


def render_dashboard(repo_root: Path | None = None) -> str:
    root = (repo_root or Path.cwd()).resolve()
    projections = list_task_status_projections(root)
    lines = [
        "Dev-Flow Control Room",
        f"root: {root}",
        "",
        f"{'Task':<10} {'Status':<20} {'Verify':<12} {'Worker':<8} Latest",
        "-" * 82,
    ]
    if not projections:
        lines.append("No tasks found.")
    for projection in projections:
        task = projection.task
        lines.append(
            f"{task.id:<10} {task.status:<20} {projection.verification_status:<12} "
            f"{task.worker:<8} {projection.latest}"
        )
        lines.append(f"  workspace: {task.workspace}")
        if task.log_path:
            lines.append(f"  log: {task.log_path}")
        if task.result_path:
            lines.append(f"  result: {task.result_path}")
        if projection.verification_exit_code is not None:
            lines.append(f"  verification_exit_code: {projection.verification_exit_code}")
        if projection.verification_log_path:
            lines.append(f"  verification_log: {projection.verification_log_path}")
        if projection.merge_ready is not None:
            merge_ready = "yes" if projection.merge_ready else "no"
            lines.append(f"  merge_ready: {merge_ready}")
    return "\n".join(lines) + "\n"


def run_dashboard(refresh_seconds: int = 0) -> None:
    while True:
        if refresh_seconds:
            os.system("clear")
        print(render_dashboard(Path.cwd()), end="")
        if not refresh_seconds:
            return
        time.sleep(refresh_seconds)
