from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from devflow.loop import pipeline_run as pr
from devflow.loop.source_snapshot import (
    SnapshotConflictError,
    SnapshotRequest,
    SnapshotValidationError,
    create_source_snapshot,
)


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "dev@example.com")
    _git(repo, "config", "user.name", "Dev")
    (repo / "src").mkdir()
    (repo / "src" / "a.py").write_text("print('a')\n", encoding="utf-8")
    (repo / "src" / "b.py").write_text("print('b')\n", encoding="utf-8")
    (repo / "docs").mkdir()
    (repo / "docs" / "note.md").write_text("# note\n", encoding="utf-8")
    (repo / ".gitignore").write_text("ignored.txt\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "-c", "commit.gpgsign=false", "commit", "-q", "-m", "init")
    (repo / "ignored.txt").write_text("nope\n", encoding="utf-8")
    (repo / ".env").write_text("SECRET=1\n", encoding="utf-8")
    (repo / "id_rsa").write_text("-----BEGIN PRIVATE KEY-----\n", encoding="utf-8")
    return repo


def _request(repo: Path, root: Path, run_id: str, **overrides) -> SnapshotRequest:
    base = _git(repo, "rev-parse", "HEAD")
    kwargs = dict(
        repo=repo,
        root=root,
        run_id=run_id,
        snapshot_id="snap-01",
        plan_hash="a" * 64,
        base_commit=base,
        selected_paths=["src/a.py", "src/b.py"],
    )
    kwargs.update(overrides)
    return SnapshotRequest(**kwargs)


def _make_run(root: Path) -> str:
    return pr.create_pipeline_run(root, {"title": "snapshot run"})


# --- path validation -----------------------------------------------------


@pytest.mark.parametrize(
    "bad",
    [
        ["/etc/passwd"],
        ["../outside.py"],
        ["src\\a.py"],
        ["src/a.py", "src/a.py"],
        ["src/missing.py"],
        ["src"],
        ["docs"],
    ],
    ids=["absolute", "traversal", "backslash", "duplicate", "missing", "dir", "dir2"],
)
def test_rejects_invalid_paths(tmp_path: Path, repo: Path, bad: list[str]) -> None:
    root = tmp_path / "state"
    run_id = _make_run(root)
    with pytest.raises(SnapshotValidationError):
        create_source_snapshot(_request(repo, root, run_id, selected_paths=bad))


def test_rejects_gitignored_path(tmp_path: Path, repo: Path) -> None:
    root = tmp_path / "state"
    run_id = _make_run(root)
    with pytest.raises(SnapshotValidationError):
        create_source_snapshot(
            _request(repo, root, run_id, selected_paths=["ignored.txt"])
        )


@pytest.mark.parametrize("secret", [".env", "id_rsa"])
def test_rejects_secret_paths(tmp_path: Path, repo: Path, secret: str) -> None:
    root = tmp_path / "state"
    run_id = _make_run(root)
    with pytest.raises(SnapshotValidationError):
        create_source_snapshot(
            _request(repo, root, run_id, selected_paths=[secret])
        )


# --- happy path / determinism -------------------------------------------


def test_creates_immutable_receipt_bound_to_inputs(tmp_path: Path, repo: Path) -> None:
    root = tmp_path / "state"
    run_id = _make_run(root)
    receipt = create_source_snapshot(_request(repo, root, run_id))

    assert receipt.snapshot_id == "snap-01"
    assert receipt.plan_hash == "a" * 64
    assert receipt.selected_paths == ["src/a.py", "src/b.py"]
    assert set(receipt.file_hashes) == {"src/a.py", "src/b.py"}
    assert receipt.tree and receipt.commit and receipt.ref
    assert receipt.fingerprint
    assert receipt.ref == f"refs/devflow/snapshots/{run_id}/snap-01"
    # ref points at the recorded commit
    assert _git(repo, "rev-parse", receipt.ref) == receipt.commit
    # commit tree matches
    assert _git(repo, "rev-parse", f"{receipt.commit}^{{tree}}") == receipt.tree


def test_identical_request_is_idempotent(tmp_path: Path, repo: Path) -> None:
    root = tmp_path / "state"
    run_id = _make_run(root)
    first = create_source_snapshot(_request(repo, root, run_id))
    second = create_source_snapshot(_request(repo, root, run_id))
    assert first.commit == second.commit
    assert first.model_dump() == second.model_dump()


def test_conflicting_replay_rejected_and_preserves_original(
    tmp_path: Path, repo: Path
) -> None:
    root = tmp_path / "state"
    run_id = _make_run(root)
    original = create_source_snapshot(_request(repo, root, run_id))
    with pytest.raises(SnapshotConflictError):
        create_source_snapshot(
            _request(repo, root, run_id, selected_paths=["src/a.py"])
        )
    # original receipt preserved on disk
    records = pr.load_pipeline_run(root, run_id)
    key = f"snapshot-{original.snapshot_id}.json"
    assert records[key]["commit"] == original.commit
    assert records[key]["selected_paths"] == ["src/a.py", "src/b.py"]


def test_preserves_operator_index_branch_worktree(tmp_path: Path, repo: Path) -> None:
    root = tmp_path / "state"
    run_id = _make_run(root)
    status_before = _git(repo, "status", "--porcelain")
    branch_before = _git(repo, "rev-parse", "HEAD")
    index_before = _git(repo, "write-tree")

    create_source_snapshot(_request(repo, root, run_id))

    assert _git(repo, "status", "--porcelain") == status_before
    assert _git(repo, "rev-parse", "HEAD") == branch_before
    assert _git(repo, "write-tree") == index_before


def test_receipt_contains_no_secret_content(tmp_path: Path, repo: Path) -> None:
    root = tmp_path / "state"
    run_id = _make_run(root)
    receipt = create_source_snapshot(_request(repo, root, run_id))
    key = f"snapshot-{receipt.snapshot_id}.json"
    raw = (
        pr.pipeline_runs_dir(root) / run_id / key
    ).read_text(encoding="utf-8")
    assert "print('a')" not in raw
    assert "print('b')" not in raw
