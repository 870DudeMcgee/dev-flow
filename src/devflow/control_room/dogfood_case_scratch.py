from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from devflow.control_room.dogfood_case_result import CaseResultRecorder, record_artifact, record_command
from devflow.control_room.paths import relative_path
from devflow.control_room.service import init_control_room


def create_recorded_git_native_case_scratch_repo(
    case_dir: Path,
    repo_name: str,
    *,
    case_result: CaseResultRecorder | None = None,
    state: dict[str, Any] | None = None,
    root: Path | None = None,
    evidence_label: str,
) -> Path:
    scratch = case_dir / "artifacts" / repo_name
    init_git_native_dogfood_repo(scratch)
    init_control_room(scratch)
    if case_result is not None:
        artifact_root = case_result.root if root is None else root
        case_result.record_artifact(scratch, root=artifact_root)
        case_result.record_command(
            f"git init scratch {evidence_label} dogfood repo",
            status="passed",
            output=relative_path(artifact_root, scratch),
        )
        return scratch
    if state is None or root is None:
        raise TypeError("case_result or both state and root are required")
    record_artifact(state, scratch, root=root)
    record_command(state, f"git init scratch {evidence_label} dogfood repo", status="passed", output=relative_path(root, scratch))
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
