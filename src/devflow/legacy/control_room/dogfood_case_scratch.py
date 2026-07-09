from __future__ import annotations

import subprocess
from pathlib import Path

from devflow.legacy.control_room.dogfood_case_result import CaseResultRecorder
from devflow.legacy.control_room.paths import relative_path
from devflow.legacy.control_room.service import init_control_room


def create_recorded_git_native_case_scratch_repo(
    case_dir: Path,
    repo_name: str,
    *,
    case_result: CaseResultRecorder,
    evidence_label: str,
) -> Path:
    scratch = case_dir / "artifacts" / repo_name
    init_git_native_dogfood_repo(scratch)
    init_control_room(scratch)
    case_result.record_artifact(scratch)
    case_result.record_command(
        f"git init scratch {evidence_label} dogfood repo",
        status="passed",
        output=relative_path(case_result.root, scratch),
    )
    return scratch


def init_git_native_dogfood_repo(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-b", "main"], cwd=root, check=True, capture_output=True, text=True, timeout=20)
    subprocess.run(["git", "config", "user.email", "dogfood@example.com"], cwd=root, check=True, capture_output=True, text=True, timeout=20)
    subprocess.run(["git", "config", "user.name", "Dogfood Test"], cwd=root, check=True, capture_output=True, text=True, timeout=20)
    (root / ".gitignore").write_text(".devflow/\n", encoding="utf-8")
    (root / "README.md").write_text("# Git-native Dogfood Repo\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=root, check=True, capture_output=True, text=True, timeout=20)
    subprocess.run(["git", "commit", "-m", "baseline"], cwd=root, check=True, capture_output=True, text=True, timeout=20)
