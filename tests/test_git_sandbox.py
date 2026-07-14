"""Behavioral tests for the deterministic git sandbox lifecycle.

These exercise the real git-worktree chain (create -> idempotent replay ->
cleanup) and the fail-closed ownership/capacity/binding guards. A fresh git
repo is materialized per test so the tests are self-contained and hermetic.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from devflow.loop.adapter import create_run_with_state
from devflow.loop.execution_authorization import authorize_execution
from devflow.loop.execution_plan import (
    ExecutionPacket,
    ExecutionPlan,
    ExecutionValidator,
    execution_plan_hash,
    save_execution_plan,
)
from devflow.loop.git_sandbox import (
    CleanupReceipt,
    SandboxCapacityError,
    SandboxCleanupReceipt,
    SandboxConflictError,
    SandboxKind,
    SandboxReceipt,
    SandboxRequest,
    SandboxValidationError,
    cleanup_sandbox,
    create_sandbox,
    load_cleanup_receipt,
    load_sandbox_receipt,
    sandbox_path,
)
from devflow.loop.pipeline_run import pipeline_runs_dir
from devflow.loop.source_snapshot import SnapshotRequest, create_source_snapshot
from devflow.loop.validator_service import ValidatorRequest, run_validator


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=str(repo),
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "dev@example.com")
    _git(repo, "config", "user.name", "Dev")
    _git(repo, "config", "commit.gpgsign", "false")
    (repo / ".gitignore").write_text(".devflow/\n", encoding="utf-8")
    (repo / "a.py").write_text("value = 1\n", encoding="utf-8")
    (repo / "b.py").write_text("value = 2\n", encoding="utf-8")
    _git(repo, "add", ".gitignore", "a.py", "b.py")
    _git(repo, "commit", "-q", "-m", "base")
    return repo


def _seed_authorized_run(tmp_path: Path, repo: Path) -> tuple[str, "ExecutionPlan"]:
    run_id, _ = create_run_with_state(repo, {"repo": str(repo)})
    plan = ExecutionPlan(
        target_files=["a.py", "b.py"],
        packets=[
            ExecutionPacket(id="packet-a", target_files=["a.py"]),
            ExecutionPacket(id="packet-b", target_files=["b.py"], depends_on=["packet-a"]),
        ],
        validators=[
            ExecutionValidator(
                id="syntax",
                argv=["python", "-m", "py_compile", "a.py", "b.py"],
                evidence=["exit-code"],
            )
        ],
    )
    save_execution_plan(repo, run_id, plan)
    plan_hash = execution_plan_hash(plan)
    snapshot = create_source_snapshot(
        SnapshotRequest(
            repo=repo,
            root=repo,
            run_id=run_id,
            snapshot_id="snap-1",
            plan_hash=plan_hash,
            base_commit=_git(repo, "rev-parse", "HEAD"),
            selected_paths=plan.target_files,
        )
    )
    validator_receipt = run_validator(
        repo,
        repo,
        ValidatorRequest(
            receipt_id="validator-syntax-1",
            run_id=run_id,
            snapshot_fingerprint=snapshot.fingerprint,
            execution_plan_hash=plan_hash,
            validator=plan.validators[0],
        ),
    )
    authorize_execution(
        repo,
        run_id,
        authorization_id="auth-1",
        snapshot_id=snapshot.snapshot_id,
        validator_receipt_ids=[validator_receipt.receipt_id],
    )
    return run_id, plan


# ---------------------------------------------------------------------------
# Packet + integration sandbox creation
# ---------------------------------------------------------------------------
def test_packet_sandbox_materializes_exact_head_and_kind(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    run_id, plan = _seed_authorized_run(tmp_path, repo)

    request = create_sandbox(
        SandboxRequest(
            repo=repo,
            root=repo,
            run_id=run_id,
            sandbox_id="sb-a",
            kind=SandboxKind.packet,
            authorization_id="auth-1",
            packet_id="packet-a",
        )
    )
    assert isinstance(request, SandboxReceipt)
    assert request.kind is SandboxKind.packet
    assert request.packet_id == "packet-a"
    assert (
        request.path
        == str(sandbox_path(repo, run_id, SandboxKind.packet, "sb-a"))
    )
    head = _git(Path(request.path), "rev-parse", "HEAD")
    # The worktree is pinned to the immutable snapshot commit, not repo HEAD.
    assert head == request.snapshot_commit

    # Integration sandbox requires packet_id None.
    integration = create_sandbox(
        SandboxRequest(
            repo=repo,
            root=repo,
            run_id=run_id,
            sandbox_id="sb-int",
            kind=SandboxKind.integration,
            authorization_id="auth-1",
            max_sandboxes=2,
        )
    )
    assert integration.kind is SandboxKind.integration
    assert integration.packet_id is None


def test_invalid_kind_binding_is_rejected(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    run_id, plan = _seed_authorized_run(tmp_path, repo)

    # packet sandbox without packet_id
    with pytest.raises(SandboxValidationError):
        create_sandbox(
            SandboxRequest(
                repo=repo,
                root=repo,
                run_id=run_id,
                sandbox_id="sb-x",
                kind=SandboxKind.packet,
                authorization_id="auth-1",
            )
        )

    # integration sandbox with a packet_id
    with pytest.raises(SandboxValidationError):
        create_sandbox(
            SandboxRequest(
                repo=repo,
                root=repo,
                run_id=run_id,
                sandbox_id="sb-x",
                kind=SandboxKind.integration,
                authorization_id="auth-1",
                packet_id="packet-a",
            )
        )


def test_authorized_dependent_packet_can_be_materialized_but_unknown_is_rejected(
    tmp_path: Path,
) -> None:
    repo = _init_repo(tmp_path)
    run_id, plan = _seed_authorized_run(tmp_path, repo)

    # Sandbox materialization is authorization-scoped. Dynamic dependency
    # readiness is enforced by advance_run immediately before a packet starts.
    dependent = create_sandbox(
        SandboxRequest(
            repo=repo,
            root=repo,
            run_id=run_id,
            sandbox_id="sb-b",
            kind=SandboxKind.packet,
            authorization_id="auth-1",
            packet_id="packet-b",
        )
    )
    assert dependent.packet_id == "packet-b"

    # packet id not in plan
    with pytest.raises(SandboxValidationError):
        create_sandbox(
            SandboxRequest(
                repo=repo,
                root=repo,
                run_id=run_id,
                sandbox_id="sb-c",
                kind=SandboxKind.packet,
                authorization_id="auth-1",
                packet_id="packet-nonexistent",
            )
        )


# ---------------------------------------------------------------------------
# Idempotent identical replay / conflicting replay
# ---------------------------------------------------------------------------
def test_identical_replay_is_idempotent_returns_existing(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    run_id, plan = _seed_authorized_run(tmp_path, repo)
    req_cls = SandboxRequest

    req = req_cls(
        repo=repo,
        root=repo,
        run_id=run_id,
        sandbox_id="sb-a",
        kind=SandboxKind.packet,
        authorization_id="auth-1",
        packet_id="packet-a",
    )
    first = create_sandbox(req)
    second = create_sandbox(req)
    assert first == second
    # Exactly one worktree registered at the path.
    assert (
        _git(repo, "worktree", "list", "--porcelain").count(
            str(sandbox_path(repo, run_id, SandboxKind.packet, "sb-a"))
        )
        == 1
    )
    assert load_sandbox_receipt(repo, run_id, "sb-a") == first


def test_conflicting_replay_fails_closed_preserves_original(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    run_id, plan = _seed_authorized_run(tmp_path, repo)
    req_cls = SandboxRequest

    first = create_sandbox(
        req_cls(
            repo=repo,
            root=repo,
            run_id=run_id,
            sandbox_id="sb-a",
            kind=SandboxKind.packet,
            authorization_id="auth-1",
            packet_id="packet-a",
        )
    )
    path = pipeline_runs_dir(repo) / run_id / "sandbox-receipts" / "sb-a.json"
    before = path.read_bytes()

    # Different kind with the same id => conflict.
    with pytest.raises(SandboxConflictError):
        create_sandbox(
            req_cls(
                repo=repo,
                root=repo,
                run_id=run_id,
                sandbox_id="sb-a",
                kind=SandboxKind.integration,
                authorization_id="auth-1",
            )
        )
    assert path.read_bytes() == before
    assert load_sandbox_receipt(repo, run_id, "sb-a") == first


# ---------------------------------------------------------------------------
# Capacity released by cleanup
# ---------------------------------------------------------------------------
def test_cleanup_releases_capacity(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    run_id, plan = _seed_authorized_run(tmp_path, repo)
    req_cls = SandboxRequest

    create_sandbox(
        req_cls(
            repo=repo,
            root=repo,
            run_id=run_id,
            sandbox_id="sb-a",
            kind=SandboxKind.packet,
            authorization_id="auth-1",
            packet_id="packet-a",
            max_sandboxes=1,
        )
    )
    # At capacity: a second creation must raise.
    with pytest.raises(SandboxCapacityError):
        create_sandbox(
            req_cls(
                repo=repo,
                root=repo,
                run_id=run_id,
                sandbox_id="sb-b",
                kind=SandboxKind.integration,
                authorization_id="auth-1",
                max_sandboxes=1,
            )
        )

    # Cleanup releases capacity.
    cleanup = cleanup_sandbox(repo, repo, run_id, "sb-a", "cl-a")
    assert isinstance(cleanup, SandboxCleanupReceipt)
    assert cleanup.removed is True
    assert not Path(cleanup.path).exists()

    # Now a second sandbox fits.
    second = create_sandbox(
        req_cls(
            repo=repo,
            root=repo,
            run_id=run_id,
            sandbox_id="sb-b",
            kind=SandboxKind.integration,
            authorization_id="auth-1",
            max_sandboxes=1,
        )
    )
    assert second.sandbox_id == "sb-b"


# ---------------------------------------------------------------------------
# Cleanup ownership / idempotency / conflict
# ---------------------------------------------------------------------------
def test_positive_cleanup_and_idempotent_replay(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    run_id, plan = _seed_authorized_run(tmp_path, repo)
    req_cls = SandboxRequest

    create_sandbox(
        req_cls(
            repo=repo,
            root=repo,
            run_id=run_id,
            sandbox_id="sb-a",
            kind=SandboxKind.packet,
            authorization_id="auth-1",
            packet_id="packet-a",
        )
    )
    first = cleanup_sandbox(repo, repo, run_id, "sb-a", "cl-a")
    second = cleanup_sandbox(repo, repo, run_id, "sb-a", "cl-a")
    assert first == second
    assert load_cleanup_receipt(repo, run_id, "cl-a") == first


def test_concurrent_conflicting_cleanup_fails_closed(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    run_id, plan = _seed_authorized_run(tmp_path, repo)
    req_cls = SandboxRequest

    create_sandbox(
        req_cls(
            repo=repo,
            root=repo,
            run_id=run_id,
            sandbox_id="sb-a",
            kind=SandboxKind.packet,
            authorization_id="auth-1",
            packet_id="packet-a",
            max_sandboxes=2,
        )
    )
    create_sandbox(
        req_cls(
            repo=repo,
            root=repo,
            run_id=run_id,
            sandbox_id="sb-b",
            kind=SandboxKind.integration,
            authorization_id="auth-1",
            max_sandboxes=2,
        )
    )
    cleanup_sandbox(repo, repo, run_id, "sb-a", "cl-a")
    # Reuse cleanup id for a different sandbox => conflict, original preserved.
    with pytest.raises(SandboxConflictError):
        cleanup_sandbox(repo, repo, run_id, "sb-b", "cl-a")
    assert load_cleanup_receipt(repo, run_id, "cl-a").sandbox_id == "sb-a"


# ---------------------------------------------------------------------------
# Corrupt / malformed stores fail closed
# ---------------------------------------------------------------------------
def test_corrupt_cleanup_store_fails_closed(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    run_id, plan = _seed_authorized_run(tmp_path, repo)
    req_cls = SandboxRequest

    create_sandbox(
        req_cls(
            repo=repo,
            root=repo,
            run_id=run_id,
            sandbox_id="sb-a",
            kind=SandboxKind.packet,
            authorization_id="auth-1",
            packet_id="packet-a",
        )
    )
    cleanup_dir = pipeline_runs_dir(repo) / run_id / "sandbox-cleanups"
    cleanup_dir.mkdir(exist_ok=True)
    # stem must equal cleanup_id; write a corrupt file that does not satisfy
    # the strict model -> fails closed on active accounting.
    (cleanup_dir / "cl-a.json").write_text("{ not valid json\n", encoding="utf-8")
    with pytest.raises(SandboxValidationError):
        cleanup_sandbox(repo, repo, run_id, "sb-a", "cl-a")


def test_cleanup_receipt_stem_must_match_id(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    run_id, plan = _seed_authorized_run(tmp_path, repo)
    req_cls = SandboxRequest

    create_sandbox(
        req_cls(
            repo=repo,
            root=repo,
            run_id=run_id,
            sandbox_id="sb-a",
            kind=SandboxKind.packet,
            authorization_id="auth-1",
            packet_id="packet-a",
        )
    )
    cleanup_dir = pipeline_runs_dir(repo) / run_id / "sandbox-cleanups"
    cleanup_dir.mkdir(exist_ok=True)
    # Valid JSON but filename stem != cleanup_id -> fails closed.
    payload = {
        "cleanup_id": "cl-other",
        "sandbox_id": "sb-a",
        "run_id": run_id,
        "kind": "packet",
        "path": "/tmp/x",
        "snapshot_commit": "0" * 40,
        "removed": True,
    }
    (cleanup_dir / "cl-a.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    with pytest.raises(SandboxValidationError):
        cleanup_sandbox(repo, repo, run_id, "sb-a", "cl-a")


# ---------------------------------------------------------------------------
# Traversal / operator preservation
# ---------------------------------------------------------------------------
def test_refuses_operator_checkout_and_preserves_unrelated_worktrees(
    tmp_path: Path,
) -> None:
    repo = _init_repo(tmp_path)
    run_id, plan = _seed_authorized_run(tmp_path, repo)
    req_cls = SandboxRequest

    # An unrelated operator worktree must survive cleanup of our sandbox.
    branch_worktree = repo / ".devflow" / "sandboxes" / run_id / "operator-wt"
    branch_worktree.parent.mkdir(parents=True, exist_ok=True)
    _git(repo, "worktree", "add", "-b", "operator-branch", str(branch_worktree))

    create_sandbox(
        req_cls(
            repo=repo,
            root=repo,
            run_id=run_id,
            sandbox_id="sb-a",
            kind=SandboxKind.packet,
            authorization_id="auth-1",
            packet_id="packet-a",
        )
    )
    cleanup_sandbox(repo, repo, run_id, "sb-a", "cl-a")

    # Operator worktree untouched.
    assert branch_worktree.exists()
    assert (
        _git(repo, "worktree", "list", "--porcelain").count(str(branch_worktree))
        == 1
    )

    # Cleanup must refuse to touch the operator checkout itself.
    receipt_dir = pipeline_runs_dir(repo) / run_id / "sandbox-receipts"
    operator_receipt = receipt_dir / "sb-op.json"
    operator_receipt.write_text(
        json.dumps(
            {
                "sandbox_id": "sb-op",
                "run_id": run_id,
                "kind": "packet",
                "authorization_id": "auth-1",
                "packet_id": "packet-a",
                "path": str(repo),
                "snapshot_ref": "refs/devflow/snapshots/x/y",
                "snapshot_commit": "0" * 40,
                "plan_hash": "0" * 64,
                "execution_plan_hash": "0" * 64,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    with pytest.raises(SandboxValidationError):
        cleanup_sandbox(repo, repo, run_id, "sb-op", "cl-op")


def test_unregistered_path_never_removed_by_remove_worktree(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    run_id, plan = _seed_authorized_run(tmp_path, repo)
    req_cls = SandboxRequest

    create_sandbox(
        req_cls(
            repo=repo,
            root=repo,
            run_id=run_id,
            sandbox_id="sb-a",
            kind=SandboxKind.packet,
            authorization_id="auth-1",
            packet_id="packet-a",
        )
    )
    # A directory that exists but is NOT a registered git worktree must never
    # be removed by cleanup's internal removal helper.
    stray = repo / ".devflow" / "sandboxes" / run_id / "stray-dir"
    stray.mkdir(parents=True)
    from devflow.loop.git_sandbox import _remove_worktree

    _remove_worktree(repo, stray)
    assert stray.exists()

    # Cleanup also refuses a receipt whose path is not the deterministic path.
    receipt_path = (
        pipeline_runs_dir(repo) / run_id / "sandbox-receipts" / "sb-a.json"
    )
    receipt_path.chmod(0o644)
    data = json.loads(receipt_path.read_text())
    data["path"] = str(repo / "somewhere-else")
    receipt_path.write_text(
        json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    receipt_path.chmod(0o444)
    with pytest.raises(SandboxValidationError):
        cleanup_sandbox(repo, repo, run_id, "sb-a", "cl-a")


# ---------------------------------------------------------------------------
# Exports / aliases
# ---------------------------------------------------------------------------
def test_cleanup_receipt_alias_exported() -> None:
    assert CleanupReceipt is SandboxCleanupReceipt
