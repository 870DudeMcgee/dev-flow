"""Compact Git status probe for the DevFlow status board."""

from __future__ import annotations

import subprocess
from pathlib import Path

_GIT_TIMEOUT_SECONDS = 2.0


def git_status_snapshot(repo_root: Path) -> dict:
    """Return a compact, read-only Git status payload for the topbar."""
    root = repo_root.resolve()
    try:
        top_level = _git(root, "rev-parse", "--show-toplevel").strip()
    except (OSError, subprocess.SubprocessError) as exc:
        return {
            "available": False,
            "status": "unknown",
            "label": "Not a git repo",
            "reason": str(exc),
            "repo_path": str(root),
        }

    repo_path = Path(top_level)
    branch = _safe_git(repo_path, "branch", "--show-current") or _safe_git(repo_path, "rev-parse", "--short", "HEAD") or "detached"
    commit = _safe_git(repo_path, "rev-parse", "--short", "HEAD") or "unknown"
    upstream = _safe_git(repo_path, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
    status_text = _safe_git(repo_path, "status", "--porcelain=v1", "--branch") or ""
    counts = _parse_porcelain_status(status_text)
    changes = _parse_porcelain_changes(status_text)

    ahead = counts["ahead"]
    behind = counts["behind"]
    dirty = counts["staged"] + counts["unstaged"] + counts["untracked"]

    if dirty:
        state = "dirty"
        label = f"{dirty} change{'s' if dirty != 1 else ''}"
    elif ahead:
        state = "unpushed"
        label = f"{ahead} unpushed"
    elif behind:
        state = "behind"
        label = f"{behind} behind"
    elif not upstream:
        state = "clean"
        label = "Clean tree"
    else:
        state = "clean"
        label = "Clean + pushed"

    return {
        "available": True,
        "repo_name": repo_path.name,
        "repo_path": str(repo_path),
        "branch": branch,
        "commit": commit,
        "upstream": upstream,
        "state": state,
        "label": label,
        "clean": dirty == 0,
        "pushed": bool(upstream) and ahead == 0,
        "ahead": ahead,
        "behind": behind,
        "staged": counts["staged"],
        "unstaged": counts["unstaged"],
        "untracked": counts["untracked"],
        "changes": changes,
    }


def _git(repo_root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo_root), *args],
        check=True,
        capture_output=True,
        text=True,
        timeout=_GIT_TIMEOUT_SECONDS,
    ).stdout


def _safe_git(repo_root: Path, *args: str) -> str:
    try:
        return _git(repo_root, *args).strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def _parse_porcelain_status(status_text: str) -> dict[str, int]:
    counts = {"ahead": 0, "behind": 0, "staged": 0, "unstaged": 0, "untracked": 0}
    for line in status_text.splitlines():
        if line.startswith("## "):
            counts["ahead"] = _parse_count(line, "ahead")
            counts["behind"] = _parse_count(line, "behind")
            continue
        if line.startswith("??"):
            counts["untracked"] += 1
            continue
        if len(line) >= 2:
            if line[0] not in {" ", "?"}:
                counts["staged"] += 1
            if line[1] not in {" ", "?"}:
                counts["unstaged"] += 1
    return counts


def _parse_porcelain_changes(status_text: str) -> list[dict[str, str]]:
    changes: list[dict[str, str]] = []
    for line in status_text.splitlines():
        if not line or line.startswith("## "):
            continue
        if line.startswith("??"):
            changes.append({
                "path": line[3:].strip(),
                "index": "?",
                "worktree": "?",
                "label": "untracked",
                "tone": "untracked",
            })
            continue
        if len(line) < 4:
            continue
        index_status = line[0]
        worktree_status = line[1]
        changes.append({
            "path": line[3:].strip(),
            "index": index_status,
            "worktree": worktree_status,
            "label": _change_label(index_status, worktree_status),
            "tone": _change_tone(index_status, worktree_status),
        })
    return changes


def _change_label(index_status: str, worktree_status: str) -> str:
    staged = index_status != " "
    unstaged = worktree_status != " "
    if staged and unstaged:
        return "staged + unstaged"
    if staged:
        return _status_name(index_status, fallback="staged")
    if unstaged:
        return _status_name(worktree_status, fallback="unstaged")
    return "clean"


def _change_tone(index_status: str, worktree_status: str) -> str:
    if index_status == "?" or worktree_status == "?":
        return "untracked"
    if index_status != " " and worktree_status != " ":
        return "mixed"
    if index_status != " ":
        return "staged"
    return "unstaged"


def _status_name(status: str, *, fallback: str) -> str:
    return {
        "A": "added",
        "C": "copied",
        "D": "deleted",
        "M": "modified",
        "R": "renamed",
        "T": "type changed",
        "U": "unmerged",
    }.get(status, fallback)


def _parse_count(line: str, label: str) -> int:
    marker = f"{label} "
    if marker not in line:
        return 0
    tail = line.split(marker, 1)[1]
    digits = []
    for char in tail:
        if char.isdigit():
            digits.append(char)
        else:
            break
    return int("".join(digits)) if digits else 0
