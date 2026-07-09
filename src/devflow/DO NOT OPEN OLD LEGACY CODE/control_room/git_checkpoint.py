from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from devflow.legacy.control_room.git_state import GitStateError, inspect_git_state, require_repo


@dataclass(frozen=True)
class CheckpointResult:
    preview_only: bool
    committed: bool
    branch: str | None
    before_head: str | None
    after_head: str | None
    message: str
    changed_files: tuple[str, ...]


def preview_checkpoint(root: Path, *, message: str) -> CheckpointResult:
    return checkpoint(root, message=message, yes=False)


def checkpoint(root: Path, *, message: str, yes: bool) -> CheckpointResult:
    repo = require_repo(root)
    clean_message = message.strip()
    if not clean_message:
        raise GitStateError("Refusing git checkpoint: --message must not be empty.")

    state = inspect_git_state(repo)
    if state.operation_in_progress:
        raise GitStateError(f"Refusing git checkpoint: Git {state.operation_in_progress} is in progress.")
    if state.conflicted_files:
        raise GitStateError("Refusing git checkpoint: conflicted files are present.")
    if state.branch != "main":
        raise GitStateError(f"Refusing git checkpoint: current branch is {state.branch or 'detached'}, expected main.")
    if state.main_diverged_origin_main:
        raise GitStateError("Refusing git checkpoint: local main and origin/main have diverged.")
    if state.main_behind_origin_main and state.main_behind_origin_main > 0:
        raise GitStateError("Refusing git checkpoint: origin/main is ahead of local main.")

    changed_files = _changed_files(repo)
    if not changed_files:
        raise GitStateError("No changes to checkpoint.")

    if not yes:
        return CheckpointResult(
            preview_only=True,
            committed=False,
            branch=state.branch,
            before_head=state.head_sha,
            after_head=state.head_sha,
            message=clean_message,
            changed_files=changed_files,
        )

    _git(repo, ["add", "-A"], check=True)
    staged_files = _staged_files(repo)
    if not staged_files:
        raise GitStateError("No staged changes to checkpoint after git add -A.")
    _git(repo, ["commit", "-m", clean_message], check=True)
    after = inspect_git_state(repo)
    return CheckpointResult(
        preview_only=False,
        committed=True,
        branch=after.branch,
        before_head=state.head_sha,
        after_head=after.head_sha,
        message=clean_message,
        changed_files=staged_files,
    )


def render_checkpoint(result: CheckpointResult) -> str:
    lines = [
        f"preview_only: {'yes' if result.preview_only else 'no'}",
        f"checkpoint: {'committed' if result.committed else 'preview'}",
        f"branch: {result.branch or 'detached'}",
        f"before_head: {result.before_head or 'unavailable'}",
        f"after_head: {result.after_head or 'unavailable'}",
        f"message: {result.message}",
        f"clean: {'yes' if result.committed else 'no'}",
        "changed_files:",
    ]
    lines.extend(f"  - {name}" for name in result.changed_files)
    if result.preview_only:
        lines.extend(
            [
                "next_action: rerun with --yes to stage and commit these changes",
                f"command: devflow git checkpoint --message {result.message!r} --yes",
            ]
        )
    else:
        lines.append("next_action: run devflow git status, then devflow push-main when ready")
    return "\n".join(lines) + "\n"


def _changed_files(repo: Path) -> tuple[str, ...]:
    proc = _git(repo, ["status", "--porcelain=v1", "-uall"], check=True)
    files: list[str] = []
    for line in proc.stdout.splitlines():
        if line:
            files.append(_status_path(line))
    return tuple(files)


def _staged_files(repo: Path) -> tuple[str, ...]:
    proc = _git(repo, ["diff", "--cached", "--name-only"], check=True)
    return tuple(line for line in proc.stdout.splitlines() if line)


def _status_path(raw_line: str) -> str:
    path = raw_line[3:] if len(raw_line) > 3 else raw_line[2:]
    path = path.strip()
    if " -> " in path:
        path = path.rsplit(" -> ", 1)[1]
    if path.startswith('"') and path.endswith('"'):
        path = path[1:-1]
    return path


def _git(cwd: Path, args: list[str], *, check: bool) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=30)
    if check and proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "git command failed").strip()
        raise GitStateError(detail)
    return proc
