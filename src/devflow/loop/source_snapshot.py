"""Phase 3 deterministic source snapshot service.

Freezes an explicitly selected set of repo-relative regular files into an
immutable Git commit via a *temporary* index, without ever touching the
operator working tree, the real index, or any branch. The only mutation is a
run-scoped ref under ``refs/devflow/snapshots/``.

Design constraints (Phase 3 contract):
  - Selected paths are explicit, deterministic, repo-relative regular files.
    Reject absolute/traversal/backslash/duplicate/missing/directory paths and
    any implicit expansion.
  - ``git check-ignore`` fails closed: ignored paths are rejected. A compact
    known-sensitive name/pattern policy also rejects obvious secret files
    (``.env`` variants, private keys, credential/token/secret names) without
    ever reading secret contents into receipts.
  - The receipt binds the approved plan hash, ordered selected paths, base
    commit, per-file SHA-256 of current selected source bytes, and an aggregate
    fingerprint.
  - A temporary ``GIT_INDEX_FILE`` is seeded with ``git read-tree <base>``,
    populated with ``git add -- <selected>``, then ``git write-tree`` /
    ``git commit-tree`` produce a deterministic commit updated only onto a
    run-scoped ref via ``git update-ref``.
  - Identical requests are idempotent; conflicting reuse of a snapshot id is
    rejected and the original immutable receipt is preserved.
  - The receipt is persisted immutably (O_EXCL) as JSON under the run
    directory and never contains source content.
  - No ``shell=True``; typed argv subprocess only.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path, PurePosixPath

from pydantic import BaseModel, ConfigDict, Field, field_validator

from devflow.loop.pipeline_run import pipeline_runs_dir

__all__ = [
    "SnapshotConflictError",
    "SnapshotError",
    "SnapshotReceipt",
    "SnapshotRequest",
    "SnapshotValidationError",
    "create_source_snapshot",
    "load_source_snapshot_receipt",
]


# Deterministic commit metadata/environment so identical input yields an
# identical commit hash (idempotency depends on this).
_DETERMINISTIC_IDENTITY = {
    "GIT_AUTHOR_NAME": "devflow-snapshot",
    "GIT_AUTHOR_EMAIL": "snapshot@devflow.local",
    "GIT_COMMITTER_NAME": "devflow-snapshot",
    "GIT_COMMITTER_EMAIL": "snapshot@devflow.local",
    "GIT_AUTHOR_DATE": "1970-01-01T00:00:00 +0000",
    "GIT_COMMITTER_DATE": "1970-01-01T00:00:00 +0000",
}

# Compact known-sensitive name/path policy. It targets conventional credential
# containers without rejecting ordinary source/docs such as tokenizers or
# token-optimization guidance.
_SECRET_BASENAME_PATTERNS = (
    re.compile(r"^\.env(\..+)?$"),
    re.compile(r"^id_(rsa|dsa|ecdsa|ed25519)$"),
    re.compile(r".*\.pem$"),
    re.compile(r".*\.key$"),
    re.compile(r".*\.p12$"),
    re.compile(r".*\.pfx$"),
    re.compile(r"^\.?(npmrc|pypirc|netrc)$"),
    re.compile(
        r"^(secret|secrets|credential|credentials|token|tokens|password|passwords)"
        r"(\.[^.]+)?$"
    ),
)
_SECRET_PATH_COMPONENTS = {".aws", ".ssh", ".gnupg"}


class SnapshotError(Exception):
    """Base class for snapshot service failures."""


class SnapshotValidationError(SnapshotError):
    """Raised when a request or selected path violates the Phase 3 contract."""


class SnapshotConflictError(SnapshotError):
    """Raised when a snapshot id is reused with a conflicting request."""


class SnapshotRequest(BaseModel):
    """Typed, explicit request to freeze selected source files."""

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    repo: Path
    root: Path
    run_id: str = Field(min_length=1, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    snapshot_id: str = Field(min_length=1, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    plan_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    base_commit: str = Field(pattern=r"^(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})$")
    selected_paths: list[str] = Field(min_length=1)

    @field_validator("selected_paths")
    @classmethod
    def _no_implicit_expansion(cls, values: list[str]) -> list[str]:
        # Reject glob-like implicit expansion tokens up front; explicit only.
        for value in values:
            if any(ch in value for ch in "*?[]"):
                raise ValueError(f"implicit path expansion is forbidden: {value!r}")
        return values


class SnapshotReceipt(BaseModel):
    """Immutable receipt describing a frozen source snapshot (no content)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    snapshot_id: str
    run_id: str
    plan_hash: str
    base_commit: str
    selected_paths: list[str]
    file_hashes: dict[str, str]
    tree: str
    commit: str
    ref: str
    fingerprint: str


def _git(repo: Path, *args: str, env: dict[str, str] | None = None) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=str(repo),
        env=env,
        shell=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise SnapshotError(
            f"git {' '.join(args[:2])} failed: {result.stderr.strip() or result.stdout.strip()}"
        )
    return result.stdout


def _validate_selected_path(repo: Path, value: str) -> str:
    if not isinstance(value, str) or not value.strip() or "\\" in value:
        raise SnapshotValidationError(
            f"selected path must be a nonblank POSIX relative path: {value!r}"
        )
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or path == PurePosixPath("."):
        raise SnapshotValidationError(
            f"selected path must stay inside the repo without traversal: {value!r}"
        )
    candidate = repo / value
    if candidate.is_symlink():
        raise SnapshotValidationError(
            f"selected path must not be a symbolic link: {value!r}"
        )
    resolved = candidate.resolve()
    try:
        resolved.relative_to(repo.resolve())
    except ValueError as exc:
        raise SnapshotValidationError(
            f"selected path escapes the repository: {value!r}"
        ) from exc
    if not resolved.is_file():
        raise SnapshotValidationError(
            f"selected path must be an existing regular file: {value!r}"
        )
    return value


def _is_sensitive_path(value: str) -> bool:
    path = PurePosixPath(value)
    if any(part.lower() in _SECRET_PATH_COMPONENTS for part in path.parts[:-1]):
        return True
    return any(pattern.match(path.name.lower()) for pattern in _SECRET_BASENAME_PATTERNS)


def _reject_secret_path(value: str) -> None:
    if _is_sensitive_path(value):
        raise SnapshotValidationError(
            f"selected path matches sensitive-name policy: {value!r}"
        )


def _reject_sensitive_base_paths(repo: Path, base_commit: str) -> None:
    paths = _git(repo, "ls-tree", "-r", "--name-only", base_commit).splitlines()
    sensitive = [path for path in paths if _is_sensitive_path(path)]
    if sensitive:
        raise SnapshotValidationError(
            f"base commit contains sensitive paths: {sensitive!r}"
        )


def _reject_ignored_paths(repo: Path, paths: list[str]) -> None:
    # Fail closed: git check-ignore returns 0 when at least one path is ignored.
    result = subprocess.run(
        ["git", "check-ignore", "--", *paths],
        cwd=str(repo),
        shell=False,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        ignored = [line for line in result.stdout.splitlines() if line.strip()]
        raise SnapshotValidationError(f"selected paths are gitignored: {ignored!r}")
    if result.returncode not in (0, 1):
        raise SnapshotError(
            f"git check-ignore failed closed: {result.stderr.strip()!r}"
        )


def _git_bytes(repo: Path, *args: str, env: dict[str, str] | None = None) -> bytes:
    result = subprocess.run(
        ["git", *args],
        cwd=str(repo),
        env=env,
        shell=False,
        capture_output=True,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).decode("utf-8", errors="replace").strip()
        raise SnapshotError(f"git {' '.join(args[:2])} failed: {detail}")
    return result.stdout


def _aggregate_fingerprint(
    plan_hash: str,
    base_commit: str,
    ordered_paths: list[str],
    file_hashes: dict[str, str],
) -> str:
    payload = json.dumps(
        {
            "plan_hash": plan_hash,
            "base_commit": base_commit,
            "selected_paths": ordered_paths,
            "file_hashes": {p: file_hashes[p] for p in ordered_paths},
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _receipt_path(root: Path, run_id: str, snapshot_id: str) -> Path:
    run_dir = pipeline_runs_dir(root) / run_id
    if not run_dir.is_dir():
        raise SnapshotError(f"pipeline run not found: {run_dir}")
    file_name = f"snapshot-{snapshot_id}.json"
    target = (run_dir / file_name).resolve()
    if target.name != file_name or target.parent != run_dir.resolve():
        raise SnapshotError(f"receipt path escapes run directory: {file_name!r}")
    return target


def _persist_receipt_o_excl(target: Path, receipt: SnapshotReceipt) -> bool:
    """Write immutably with O_EXCL. Return True if newly written."""
    text = json.dumps(receipt.model_dump(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    try:
        fd = os.open(str(target), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)
    except FileExistsError:
        return False
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
    except Exception:
        target.unlink(missing_ok=True)
        raise
    return True


def load_source_snapshot_receipt(
    root: Path | str, run_id: str, snapshot_id: str
) -> SnapshotReceipt:
    """Load one immutable run-scoped snapshot receipt."""
    target = _receipt_path(Path(root), run_id, snapshot_id)
    try:
        receipt = SnapshotReceipt.model_validate_json(target.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SnapshotValidationError(
            f"snapshot receipt {snapshot_id!r} is missing or corrupt"
        ) from exc
    if receipt.run_id != run_id or receipt.snapshot_id != snapshot_id:
        raise SnapshotValidationError("snapshot receipt does not match its path")
    return receipt


def create_source_snapshot(request: SnapshotRequest) -> SnapshotReceipt:
    """Freeze the selected source files and return an immutable receipt.

    Idempotent for identical requests; conflicting reuse of a snapshot id is
    rejected and the original receipt is preserved.
    """
    repo = request.repo.resolve()
    if not (repo / ".git").exists():
        raise SnapshotError(f"not a git repository: {repo}")

    # Deterministic ordering; validation runs on the exact selected order.
    ordered_paths = list(request.selected_paths)
    if len(ordered_paths) != len(set(ordered_paths)):
        raise SnapshotValidationError("selected paths must be unique")

    for value in ordered_paths:
        _validate_selected_path(repo, value)
        _reject_secret_path(value)
    _reject_ignored_paths(repo, ordered_paths)
    _reject_sensitive_base_paths(repo, request.base_commit)

    ref = f"refs/devflow/snapshots/{request.run_id}/{request.snapshot_id}"
    receipt_target = _receipt_path(request.root, request.run_id, request.snapshot_id)

    # Build the frozen commit in a temporary, isolated index. The operator's
    # real index, working tree, and branches are never touched.
    with tempfile.TemporaryDirectory() as tmpdir:
        index_file = str(Path(tmpdir) / "snapshot.index")
        env = {**os.environ, **_DETERMINISTIC_IDENTITY, "GIT_INDEX_FILE": index_file}

        _git(repo, "read-tree", request.base_commit, env=env)
        _git(repo, "add", "--", *ordered_paths, env=env)
        tree = _git(repo, "write-tree", env=env).strip()
        file_hashes = {
            path: hashlib.sha256(
                _git_bytes(repo, "cat-file", "blob", f"{tree}:{path}", env=env)
            ).hexdigest()
            for path in ordered_paths
        }
        fingerprint = _aggregate_fingerprint(
            request.plan_hash, request.base_commit, ordered_paths, file_hashes
        )
        commit = _git(
            repo,
            "-c",
            "commit.gpgsign=false",
            "commit-tree",
            tree,
            "-p",
            request.base_commit,
            "-m",
            f"devflow snapshot {request.snapshot_id} plan={request.plan_hash}",
            env=env,
        ).strip()

    receipt = SnapshotReceipt(
        snapshot_id=request.snapshot_id,
        run_id=request.run_id,
        plan_hash=request.plan_hash,
        base_commit=request.base_commit,
        selected_paths=ordered_paths,
        file_hashes=file_hashes,
        tree=tree,
        commit=commit,
        ref=ref,
        fingerprint=fingerprint,
    )

    # Persist immutably first; O_EXCL detects an existing snapshot id.
    if not _persist_receipt_o_excl(receipt_target, receipt):
        existing = load_source_snapshot_receipt(
            request.root, request.run_id, request.snapshot_id
        )
        if existing.model_dump() != receipt.model_dump():
            raise SnapshotConflictError(
                f"snapshot id {request.snapshot_id!r} already exists with a "
                "conflicting request; original receipt preserved"
            )
        return existing

    # New snapshot: point the run-scoped ref only (never a branch). If ref
    # creation fails, remove the just-created receipt so partial state cannot
    # masquerade as a usable snapshot.
    try:
        _git(repo, "update-ref", ref, commit, "")
    except Exception:
        receipt_target.chmod(0o644)
        receipt_target.unlink(missing_ok=True)
        raise
    return receipt
