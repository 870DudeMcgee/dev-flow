from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


class GitStateError(ValueError):
    pass


@dataclass(frozen=True)
class GitDirtyCounts:
    staged: int = 0
    unstaged: int = 0
    untracked: int = 0


@dataclass(frozen=True)
class GitState:
    is_repo: bool
    repo_root: str | None
    branch: str | None
    head_sha: str | None
    origin_main_sha: str | None
    dirty: bool
    counts: GitDirtyCounts
    operation_in_progress: str | None
    conflicted_files: tuple[str, ...]
    ahead_origin_main: int | None
    behind_origin_main: int | None
    main_ahead_origin_main: int | None
    main_behind_origin_main: int | None
    main_diverged_origin_main: bool
    safe_for_worker_writes: bool
    safe_for_promotion: bool
    safe_for_push: bool


def inspect_git_state(root: Path) -> GitState:
    repo_root_path = repo_root(root)
    if repo_root_path is None:
        return GitState(
            is_repo=False,
            repo_root=None,
            branch=None,
            head_sha=None,
            origin_main_sha=None,
            dirty=False,
            counts=GitDirtyCounts(),
            operation_in_progress=None,
            conflicted_files=(),
            ahead_origin_main=None,
            behind_origin_main=None,
            main_ahead_origin_main=None,
            main_behind_origin_main=None,
            main_diverged_origin_main=False,
            safe_for_worker_writes=False,
            safe_for_promotion=False,
            safe_for_push=False,
        )

    branch = current_branch(repo_root_path)
    head = head_sha(repo_root_path)
    origin = origin_main_sha(repo_root_path)
    counts, conflicts = dirty_counts(repo_root_path)
    operation = operation_in_progress(repo_root_path)
    dirty = bool(counts.staged or counts.unstaged or counts.untracked or conflicts)
    ahead = behind = main_ahead = main_behind = None
    if origin:
        ahead, behind = ahead_behind(repo_root_path, "HEAD", "origin/main")
        if ref_sha(repo_root_path, "main"):
            main_ahead, main_behind = ahead_behind(repo_root_path, "main", "origin/main")
    main_diverged = bool(main_ahead and main_behind)
    no_operation = operation is None
    clean = not dirty
    safe_for_worker_writes = no_operation and clean
    safe_for_promotion = bool(no_operation and clean and branch == "main" and not main_diverged and not (main_behind and main_behind > 0))
    safe_for_push = bool(no_operation and clean and branch == "main" and origin and not main_diverged and not (main_behind and main_behind > 0))
    return GitState(
        is_repo=True,
        repo_root=repo_root_path.as_posix(),
        branch=branch,
        head_sha=head,
        origin_main_sha=origin,
        dirty=dirty,
        counts=counts,
        operation_in_progress=operation,
        conflicted_files=conflicts,
        ahead_origin_main=ahead,
        behind_origin_main=behind,
        main_ahead_origin_main=main_ahead,
        main_behind_origin_main=main_behind,
        main_diverged_origin_main=main_diverged,
        safe_for_worker_writes=safe_for_worker_writes,
        safe_for_promotion=safe_for_promotion,
        safe_for_push=safe_for_push,
    )


def render_git_status(root: Path, *, devmode_detected: bool) -> str:
    state = inspect_git_state(root)
    if not state.is_repo:
        return "git_repo: no\nsafe_for_worker_writes: no\nsafe_for_promotion: no\nsafe_for_push: no\n"
    lines = [
        "git_repo: yes",
        f"repo_root: {state.repo_root}",
        f"branch: {state.branch or 'detached'}",
        f"head_sha: {state.head_sha or 'unavailable'}",
        f"origin_main_sha: {state.origin_main_sha or 'unavailable'}",
        f"clean: {'yes' if not state.dirty else 'no'}",
        f"dirty_state: {'dirty' if state.dirty else 'clean'}",
        f"staged_count: {state.counts.staged}",
        f"unstaged_count: {state.counts.unstaged}",
        f"untracked_count: {state.counts.untracked}",
        f"operation_in_progress: {state.operation_in_progress or 'none'}",
        f"ahead_origin_main: {_display_count(state.ahead_origin_main)}",
        f"behind_origin_main: {_display_count(state.behind_origin_main)}",
        f"main_ahead_origin_main: {_display_count(state.main_ahead_origin_main)}",
        f"main_behind_origin_main: {_display_count(state.main_behind_origin_main)}",
        f"diverged_local_main_origin_main: {'yes' if state.main_diverged_origin_main else 'no'}",
        f"safe_for_worker_writes: {'yes' if state.safe_for_worker_writes else 'no'}",
        f"safe_for_promotion: {'yes' if state.safe_for_promotion else 'no'}",
        f"safe_for_push: {'yes' if state.safe_for_push else 'no'}",
        f"devmode_detected: {'yes' if devmode_detected else 'no'}",
    ]
    if state.conflicted_files:
        lines.append("conflicted_files:")
        lines.extend(f"  - {name}" for name in state.conflicted_files)
    else:
        lines.append("conflicted_files: none")
    return "\n".join(lines) + "\n"


def sync_main(root: Path) -> str:
    repo = require_repo(root)
    state = inspect_git_state(repo)
    _refuse_operation_or_dirty(state, "sync-main")
    fetch_origin(repo)
    _git(repo, ["switch", "main"], check=True)
    state = inspect_git_state(repo)
    if state.main_diverged_origin_main:
        raise GitStateError(
            "Refusing sync-main: local main and origin/main have diverged.\n"
            "Next safe action: inspect `devflow git status`, then resolve manually with human approval."
        )
    _git(repo, ["pull", "--ff-only", "origin", "main"], check=True)
    state = inspect_git_state(repo)
    if state.main_behind_origin_main and state.main_behind_origin_main > 0:
        raise GitStateError("sync-main failed: main is still behind origin/main after ff-only pull.")
    return _sync_push_summary("sync-main", state)


def push_main(root: Path) -> str:
    repo = require_repo(root)
    from devflow.legacy.control_room.project_registry import project_publication_policy

    policy = project_publication_policy(repo)
    if policy is not None and not policy.push_allowed:
        raise GitStateError(
            "Refusing push-main: project policy disallows remote publication.\n"
            "Set .devflow/project/project.yaml remote_publication.push_allowed only after explicit human approval."
        )
    state = inspect_git_state(repo)
    if state.branch != "main":
        raise GitStateError(f"Refusing push-main: current branch is {state.branch or 'detached'}, expected main.")
    _refuse_operation_or_dirty(state, "push-main")
    fetch_origin(repo)
    state = inspect_git_state(repo)
    if state.main_diverged_origin_main:
        raise GitStateError(
            "Refusing push-main: local main and origin/main have diverged.\n"
            "Next safe action: run `devflow sync-main` only after manually resolving divergence."
        )
    if state.main_behind_origin_main and state.main_behind_origin_main > 0:
        raise GitStateError(
            "Refusing push-main: origin/main is ahead of local main.\n"
            "Next safe commands:\n"
            "  devflow git status\n"
            "  devflow sync-main"
        )
    if not state.main_ahead_origin_main:
        return _sync_push_summary("push-main", state, extra="nothing_to_push: yes")
    proc = _git(repo, ["push", "origin", "main"], check=False)
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "git push failed").strip()
        raise GitStateError(
            "push-main rejected by Git.\n"
            f"detail: {detail}\n"
            "Next safe commands:\n"
            "  devflow git status\n"
            "  devflow sync-main"
        )
    state = inspect_git_state(repo)
    return _sync_push_summary("push-main", state, extra="pushed: yes")


def require_repo(root: Path) -> Path:
    repo = repo_root(root)
    if repo is None:
        raise GitStateError("Not inside a Git repository.")
    return repo


def repo_root(root: Path) -> Path | None:
    proc = _git(root, ["rev-parse", "--show-toplevel"], check=False)
    if proc.returncode != 0:
        return None
    value = proc.stdout.strip()
    return Path(value).resolve() if value else None


def current_branch(root: Path) -> str | None:
    proc = _git(root, ["branch", "--show-current"], check=False)
    return proc.stdout.strip() or None if proc.returncode == 0 else None


def head_sha(root: Path) -> str | None:
    return ref_sha(root, "HEAD")


def origin_main_sha(root: Path) -> str | None:
    return ref_sha(root, "origin/main")


def ref_sha(root: Path, ref: str) -> str | None:
    proc = _git(root, ["rev-parse", "--verify", f"{ref}^{{commit}}"], check=False)
    if proc.returncode != 0:
        return None
    return proc.stdout.strip() or None


def dirty_counts(root: Path) -> tuple[GitDirtyCounts, tuple[str, ...]]:
    proc = _git(root, ["status", "--porcelain=v1", "-uall"], check=False)
    if proc.returncode != 0:
        return GitDirtyCounts(), ()
    staged = unstaged = untracked = 0
    conflicts: list[str] = []
    conflict_codes = {"DD", "AU", "UD", "UA", "DU", "AA", "UU"}
    for raw_line in proc.stdout.splitlines():
        if not raw_line:
            continue
        code = raw_line[:2]
        path = _status_path(raw_line)
        if code in conflict_codes:
            conflicts.append(path)
            continue
        if code == "??":
            untracked += 1
            continue
        if code[0] not in {" ", "?"}:
            staged += 1
        if code[1] not in {" ", "?"}:
            unstaged += 1
    return GitDirtyCounts(staged=staged, unstaged=unstaged, untracked=untracked), tuple(sorted(conflicts))


def operation_in_progress(root: Path) -> str | None:
    checks = (
        ("merge", "MERGE_HEAD"),
        ("rebase", "rebase-merge"),
        ("rebase", "rebase-apply"),
        ("cherry-pick", "CHERRY_PICK_HEAD"),
    )
    for name, git_path in checks:
        path = git_path_path(root, git_path)
        if path and path.exists():
            return name
    return None


def git_path_path(root: Path, path_name: str) -> Path | None:
    proc = _git(root, ["rev-parse", "--git-path", path_name], check=False)
    if proc.returncode != 0:
        return None
    value = proc.stdout.strip()
    if not value:
        return None
    path = Path(value)
    return path if path.is_absolute() else root / path


def ahead_behind(root: Path, left: str, right: str) -> tuple[int, int]:
    proc = _git(root, ["rev-list", "--left-right", "--count", f"{left}...{right}"], check=False)
    if proc.returncode != 0:
        return 0, 0
    parts = proc.stdout.strip().split()
    if len(parts) != 2:
        return 0, 0
    return int(parts[0]), int(parts[1])


def fetch_origin(root: Path) -> None:
    proc = _git(root, ["fetch", "origin"], check=False)
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "git fetch origin failed").strip()
        raise GitStateError(f"Fetch failed: {detail}")


def _refuse_operation_or_dirty(state: GitState, command_name: str) -> None:
    if state.operation_in_progress:
        raise GitStateError(f"Refusing {command_name}: Git {state.operation_in_progress} is in progress.")
    if state.dirty:
        raise GitStateError(
            f"Refusing {command_name}: working tree is dirty "
            f"(staged={state.counts.staged}, unstaged={state.counts.unstaged}, untracked={state.counts.untracked})."
        )


def _sync_push_summary(command: str, state: GitState, *, extra: str | None = None) -> str:
    lines = [
        f"{command}: ok",
        f"branch: {state.branch or 'detached'}",
        f"head_sha: {state.head_sha or 'unavailable'}",
        f"origin_main_sha: {state.origin_main_sha or 'unavailable'}",
        f"main_ahead_origin_main: {_display_count(state.main_ahead_origin_main)}",
        f"main_behind_origin_main: {_display_count(state.main_behind_origin_main)}",
    ]
    if extra:
        lines.append(extra)
    return "\n".join(lines) + "\n"


def _display_count(value: int | None) -> str:
    return str(value) if value is not None else "unavailable"


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


def git_ignored_paths(root: Path, paths: list[str]) -> set[str]:
    if not paths:
        return set()
    try:
        proc = subprocess.run(
            ["git", "check-ignore", "--stdin", "-z"],
            input="\0".join(paths),
            cwd=root,
            capture_output=True,
            text=True,
            timeout=15,
        )
        if proc.returncode not in {0, 1}:
            return set()
        return {p for p in proc.stdout.split("\0") if p}
    except Exception:
        return set()
