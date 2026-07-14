from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path

import pytest

from devflow.loop import pipeline_run as pr
from devflow.loop import source_snapshot as snapshots
from devflow.loop.source_snapshot import (
    SnapshotError,
    SnapshotRequest,
    SnapshotValidationError,
    create_source_snapshot,
    load_source_snapshot_receipt,
)


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "dev@example.com")
    _git(repo, "config", "user.name", "Dev")
    (repo / "a.py").write_text("base\n")
    _git(repo, "add", "a.py")
    _git(repo, "-c", "commit.gpgsign=false", "commit", "-q", "-m", "base")
    return repo


def _request(repo: Path, root: Path, run_id: str, **updates: object) -> SnapshotRequest:
    payload = {
        "repo": repo,
        "root": root,
        "run_id": run_id,
        "snapshot_id": "snap-1",
        "plan_hash": "a" * 64,
        "base_commit": _git(repo, "rev-parse", "HEAD"),
        "selected_paths": ["a.py"],
    }
    payload.update(updates)
    return SnapshotRequest.model_validate(payload)


def test_snapshot_requires_sha256_plan_binding_and_rejects_globs(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    root = tmp_path / "state"
    run_id = pr.create_pipeline_run(root, {"repo": "test"})
    with pytest.raises(ValueError):
        _request(repo, root, run_id, plan_hash="plan-abc")
    with pytest.raises(ValueError):
        _request(repo, root, "../escape")
    with pytest.raises(ValueError):
        _request(repo, root, run_id, base_commit="abcdef0")
    with pytest.raises(ValueError):
        _request(repo, root, run_id, selected_paths=["*.py"])


def test_snapshot_fails_closed_when_base_commit_contains_known_sensitive_path(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    (repo / ".env").write_text("TOP_SECRET=do-not-copy\n")
    _git(repo, "add", "-f", ".env")
    _git(repo, "-c", "commit.gpgsign=false", "commit", "-q", "-m", "bad base")
    root = tmp_path / "state"
    run_id = pr.create_pipeline_run(root, {"repo": "test"})

    with pytest.raises(SnapshotValidationError, match="base commit contains sensitive"):
        create_source_snapshot(_request(repo, root, run_id))

    run_dir = pr.pipeline_runs_dir(root) / run_id
    assert not (run_dir / "snapshot-snap-1.json").exists()
    assert "do-not-copy" not in "".join(
        path.read_text(errors="ignore") for path in run_dir.rglob("*") if path.is_file()
    )


def test_snapshot_receipt_is_read_only_reconstructable_and_matches_frozen_bytes(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    (repo / "a.py").write_text("dirty selected bytes\n")
    root = tmp_path / "state"
    run_id = pr.create_pipeline_run(root, {"repo": "test"})
    receipt = create_source_snapshot(_request(repo, root, run_id))

    loaded = load_source_snapshot_receipt(root, run_id, "snap-1")
    assert loaded == receipt
    frozen = _git(repo, "show", f"{receipt.commit}:a.py")
    assert frozen == "dirty selected bytes"
    path = pr.pipeline_runs_dir(root) / run_id / "snapshot-snap-1.json"
    assert os.stat(path).st_mode & 0o222 == 0


def test_snapshot_hashes_exact_frozen_blob_despite_checkout_race(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path)
    (repo / "a.py").write_text("bytes before add\n", encoding="utf-8")
    root = tmp_path / "state"
    run_id = pr.create_pipeline_run(root, {"repo": "test"})
    real_git = snapshots._git

    def mutate_before_add(repo_path: Path, *args: str, env=None) -> str:
        if args and args[0] == "add":
            (repo_path / "a.py").write_text("bytes actually added\n", encoding="utf-8")
        return real_git(repo_path, *args, env=env)

    monkeypatch.setattr(snapshots, "_git", mutate_before_add)
    receipt = create_source_snapshot(_request(repo, root, run_id))
    frozen = subprocess.run(
        ["git", "cat-file", "blob", f"{receipt.tree}:a.py"],
        cwd=repo,
        check=True,
        capture_output=True,
    ).stdout
    assert receipt.file_hashes["a.py"] == hashlib.sha256(frozen).hexdigest()


def test_update_ref_failure_removes_new_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path)
    root = tmp_path / "state"
    run_id = pr.create_pipeline_run(root, {"repo": "test"})
    real_git = snapshots._git

    def fail_update_ref(repo_path: Path, *args: str, env=None) -> str:
        if args and args[0] == "update-ref":
            raise SnapshotError("forced ref failure")
        return real_git(repo_path, *args, env=env)

    monkeypatch.setattr(snapshots, "_git", fail_update_ref)
    with pytest.raises(SnapshotError, match="forced ref failure"):
        create_source_snapshot(_request(repo, root, run_id))

    assert not (
        pr.pipeline_runs_dir(root) / run_id / "snapshot-snap-1.json"
    ).exists()
