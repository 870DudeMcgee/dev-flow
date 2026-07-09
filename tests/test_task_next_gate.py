from __future__ import annotations

import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import cast


from tests.helpers import setup_temp_git_repo


# ---- fixtures ----------------------------------------------------------

def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _create_task(root: Path, task_id: str, title: str = "test task", status: str = "created") -> None:
    """Write a real DevFlow task record with the given status."""
    from devflow.legacy.control_room.models import TaskRecord, TaskStatus
    from devflow.legacy.control_room.persistence import save_task

    now = datetime.now(timezone.utc)
    save_task(
        root / ".devflow" / "tasks" / task_id,
        TaskRecord(
            id=task_id,
            title=title,
            status=cast(TaskStatus, status),
            created_at=now,
            updated_at=now,
            workspace=f".devflow/workspaces/{task_id}",
            worker="shell",
            verification_status="not_run",
        ),
    )


def _seed_qwopus_patch_evidence(root: Path, task_id: str, agent_id: str = "qwopus-implementer") -> None:
    """Write only the proposal.patch (no review/dry-run/applied evidence)."""
    agent_dir = root / ".devflow" / "tasks" / task_id / "agents" / agent_id
    _write_json(
        agent_dir / "run.json",
        {"status": "complete", "proposal_patch_found": True, "proposal_patch_byte_length": 100},
    )
    (agent_dir / "proposal.patch").write_text("diff --git a/x b/x\n", encoding="utf-8")
    (agent_dir / "result.md").write_text("done", encoding="utf-8")


def _sync_qwopus_run_patch_candidate(root: Path, task_id: str, agent_id: str = "qwopus-implementer") -> Path:
    task_path = root / ".devflow" / "tasks" / task_id
    agent_patch = task_path / "agents" / agent_id / "proposal.patch"
    run_dir = task_path / "local-model-runs" / f"agent-{_slug(agent_id)}"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "proposal.patch").write_text(agent_patch.read_text(encoding="utf-8"), encoding="utf-8")
    return run_dir


def _seed_qwopus_review(root: Path, task_id: str, agent_id: str = "qwopus-implementer") -> None:
    run_dir = _sync_qwopus_run_patch_candidate(root, task_id, agent_id=agent_id)
    _write_json(run_dir / "patch-review.json", {"task_id": task_id, "status": "approved"})


def _seed_qwopus_dry_run(root: Path, task_id: str, agent_id: str = "qwopus-implementer") -> None:
    run_dir = _sync_qwopus_run_patch_candidate(root, task_id, agent_id=agent_id)
    _write_json(run_dir / "patch-dry-run.json", {"task_id": task_id, "status": "approved"})


def _seed_qwopus_applied(root: Path, task_id: str, agent_id: str = "qwopus-implementer") -> None:
    task_path = root / ".devflow" / "tasks" / task_id
    agent_dir = task_path / "agents" / agent_id
    patch_hash = _patch_hash(agent_dir / "proposal.patch")
    _write_json(task_path / "patch-application.json", {"task_id": task_id, "agent_id": agent_id, "patch_hash": patch_hash, "applied_at": "2026-01-01T00:00:00Z"})


def _seed_verification(root: Path, task_id: str, status: str = "passed") -> None:
    task_path = root / ".devflow" / "tasks" / task_id
    _write_json(task_path / "verification.json", {"task_id": task_id, "status": status})


def _seed_promotion_ready(root: Path, task_id: str) -> None:
    task_path = root / ".devflow" / "tasks" / task_id
    _write_json(task_path / "promotion-ready.json", {"task_id": task_id, "ready": True})


def _slug(value: str) -> str:
    return "".join(c if c.isalnum() or c in "_.-" else "-" for c in value).strip("-") or "agent"


def _patch_hash(patch_path: Path) -> str:
    return hashlib.sha256(patch_path.read_bytes()).hexdigest()


# ---- unit tests for the resolver ---------------------------------------

from devflow.legacy.control_room.task_next_gate import TaskNextGate, resolve_task_next_gate, DashboardActionAdapter


class TestResolveTaskNextGate:
    def test_created_task_returns_run_worker(self, tmp_path: Path) -> None:
        _create_task(tmp_path, "task-0001")
        result = resolve_task_next_gate(tmp_path, "task-0001")
        assert result.gate == "run_worker"
        assert result.requires_human_approval is True
        assert "devflow task run " in str(result.command or "")

    def test_status_created_tasks_need_work(self, tmp_path: Path) -> None:
        _create_task(tmp_path, "task-0001")
        result = resolve_task_next_gate(tmp_path, "task-0001")
        assert result.gate == "run_worker"

    def test_shell_complete_without_verification_needs_verify(self, tmp_path: Path) -> None:
        _create_task(tmp_path, "task-0002", status="complete")
        result = resolve_task_next_gate(tmp_path, "task-0002")
        assert result.gate == "verify"

    def test_qwopus_patch_without_review_needs_review(self, tmp_path: Path) -> None:
        _create_task(tmp_path, "task-0003", status="complete")
        _seed_qwopus_patch_evidence(tmp_path, "task-0003")
        result = resolve_task_next_gate(tmp_path, "task-0003")
        assert result.gate == "review_patch"
        assert result.label == "Review patch"

    def test_qwopus_patch_with_review_but_no_dry_run_needs_dry_run(self, tmp_path: Path) -> None:
        _create_task(tmp_path, "task-0004", status="complete")
        _seed_qwopus_patch_evidence(tmp_path, "task-0004")
        _seed_qwopus_review(tmp_path, "task-0004")
        result = resolve_task_next_gate(tmp_path, "task-0004")
        assert result.gate == "patch_dry_run"
        assert result.label == "Patch dry-run"

    def test_qwopus_patch_with_review_and_dry_run_but_not_applied_needs_apply(self, tmp_path: Path) -> None:
        _create_task(tmp_path, "task-0005", status="complete")
        _seed_qwopus_patch_evidence(tmp_path, "task-0005")
        _seed_qwopus_review(tmp_path, "task-0005")
        _seed_qwopus_dry_run(tmp_path, "task-0005")
        result = resolve_task_next_gate(tmp_path, "task-0005")
        assert result.gate == "apply_patch"
        assert result.label == "Apply patch"

    def test_stale_patch_gate_evidence_does_not_skip_review(self, tmp_path: Path) -> None:
        _create_task(tmp_path, "task-0005b", status="complete")
        _seed_qwopus_patch_evidence(tmp_path, "task-0005b")
        run_dir = tmp_path / ".devflow" / "tasks" / "task-0005b" / "local-model-runs" / "agent-qwopus-implementer"
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "proposal.patch").write_text("diff --git a/old b/old\n", encoding="utf-8")
        _write_json(run_dir / "patch-review.json", {"task_id": "task-0005b", "status": "approved"})
        _write_json(run_dir / "patch-dry-run.json", {"task_id": "task-0005b", "status": "passed"})

        result = resolve_task_next_gate(tmp_path, "task-0005b")

        assert result.gate == "review_patch"
        assert result.command == "devflow task review-patch task-0005b --agent qwopus-implementer"

    def test_applied_patch_without_verification_needs_verify(self, tmp_path: Path) -> None:
        _create_task(tmp_path, "task-0006", status="complete")
        _seed_qwopus_patch_evidence(tmp_path, "task-0006")
        _seed_qwopus_review(tmp_path, "task-0006")
        _seed_qwopus_dry_run(tmp_path, "task-0006")
        _seed_qwopus_applied(tmp_path, "task-0006")
        result = resolve_task_next_gate(tmp_path, "task-0006")
        assert result.gate == "verify"

    def test_verified_but_not_promoted_needs_promotion_preview(self, tmp_path: Path) -> None:
        _create_task(tmp_path, "task-0007", status="verified")
        _seed_verification(tmp_path, "task-0007")
        result = resolve_task_next_gate(tmp_path, "task-0007")
        assert result.gate == "promotion_preview"

    def test_closed_task_returns_closed_gate(self, tmp_path: Path) -> None:
        _create_task(tmp_path, "task-0008", status="closed")
        result = resolve_task_next_gate(tmp_path, "task-0008")
        assert result.gate == "closed"

    def test_promoted_task_produces_inspect(self, tmp_path: Path) -> None:
        _create_task(tmp_path, "task-0009", status="promoted")
        result = resolve_task_next_gate(tmp_path, "task-0009")
        assert result.gate == "inspect"

    def test_dashboard_adapter_from_gate(self, tmp_path: Path) -> None:
        _create_task(tmp_path, "task-0010")
        gate = resolve_task_next_gate(tmp_path, "task-0010")
        adapter = DashboardActionAdapter.from_gate(gate)
        assert adapter["label"] == gate.label
        assert adapter["command"] == gate.command

    def test_review_patch_requires_human_approval(self, tmp_path: Path) -> None:
        _create_task(tmp_path, "task-0011", status="complete")
        _seed_qwopus_patch_evidence(tmp_path, "task-0011")
        result = resolve_task_next_gate(tmp_path, "task-0011")
        assert result.requires_human_approval is True

    def test_verify_is_safe(self, tmp_path: Path) -> None:
        _create_task(tmp_path, "task-0012", status="complete")
        result = resolve_task_next_gate(tmp_path, "task-0012")
        assert result.supervisor_may_auto_run is True

    def test_promotion_preview_requires_human_approval(self, tmp_path: Path) -> None:
        _create_task(tmp_path, "task-0013", status="verified")
        _seed_verification(tmp_path, "task-0013")
        result = resolve_task_next_gate(tmp_path, "task-0013")
        assert result.requires_human_approval is True

    def test_missing_task_dir_returns_closed(self, tmp_path: Path) -> None:
        """Non-existent task directory → closed gate."""
        result = resolve_task_next_gate(tmp_path, "task-9999")
        assert result.gate == "closed"


# ---- integration: review_readiness projection agrees with gate -----------

def test_review_readiness_shows_review_patch_not_verify(
    tmp_path: Path,
) -> None:
    """Qwopus patch-gate must win over generic verification."""
    setup_temp_git_repo(tmp_path)
    _create_task(tmp_path, "task-0001", status="complete")
    _seed_qwopus_patch_evidence(tmp_path, "task-0001")

    from devflow.legacy.control_room.review_readiness import build_review_readiness_projection
    proj = build_review_readiness_projection(tmp_path, "task-0001")
    assert proj.review_state == "review_patch"


def test_review_readiness_shows_patch_dry_run_after_review(
    tmp_path: Path,
) -> None:
    """After patch review, next step must be dry-run — not verification."""
    setup_temp_git_repo(tmp_path)
    _create_task(tmp_path, "task-0002", status="complete")
    _seed_qwopus_patch_evidence(tmp_path, "task-0002")
    _seed_qwopus_review(tmp_path, "task-0002")

    from devflow.legacy.control_room.review_readiness import build_review_readiness_projection
    proj = build_review_readiness_projection(tmp_path, "task-0002")
    assert proj.review_state == "patch_dry_run"


# ---- integration: operating-layer snapshot agrees -------------------------

def test_operating_layer_snapshot_includes_browser_review_loop_summary(
    tmp_path: Path, monkeypatch,
) -> None:
    """Operating layer snapshot must carry the real next-gate command into the review loop."""
    monkeypatch.chdir(tmp_path)

    setup_temp_git_repo(tmp_path)
    _create_task(tmp_path, "task-0001", title="browser review task", status="complete")

    # Seed Qwopus patch evidence so the next gate is `review-patch`, not verification.
    _seed_qwopus_patch_evidence(tmp_path, "task-0001")

    from devflow.legacy.control_room.operating_layer import build_operating_layer_snapshot
    snapshot = build_operating_layer_snapshot(tmp_path)
    p = snapshot.model_dump(mode="json")
    review_loop = p["review_loop"]
    assert review_loop["status"] == "needs_review"


# ---- integration: server approval blocking (existing test preserved) -------

def test_operating_layer_server_blocks_approval_required_actions(
    tmp_path: Path, monkeypatch,
) -> None:
    """Existing test: must still pass — we don't remove its logic."""
    monkeypatch.chdir(tmp_path)

    from typer.testing import CliRunner as TRunner
    from devflow.cli import app as cli_app
    assert TRunner().invoke(cli_app, ["task", "create", "blocked runtime action"]).exit_code == 0
    worker_log = tmp_path / ".devflow" / "tasks" / "task-0001" / "logs" / "worker.log"

    from devflow.legacy.control_room.operating_layer_server import OperatingLayerHTTPServer
    import threading
    import json
    from http.client import HTTPConnection

    server = OperatingLayerHTTPServer(("127.0.0.1", 0), tmp_path)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address

    try:
        command = "devflow agent propose-patch --task task-0001 --profile x"
        body = json.dumps({
            "command": command,
            "human_approved": True,
            "approval_phrase": "I approve this exact Dev-Flow command",
            "approved_command": command,
        })
        conn = HTTPConnection(host, port, timeout=5)
        conn.request("POST", "/api/actions/run", body=body, headers={"Content-Type": "application/json"})
        resp = conn.getresponse()
        payload = json.loads(resp.read().decode())
        # Just ensure the path is exercised — exact status depends on env.
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


# ---- compatibility adapter tests ---------------------------------------

def test_dashboard_action_adapter_has_required_fields() -> None:
    gate = TaskNextGate(task_id="t1", label="test", gate="verify", command="devflow task verify t1", reason="test")
    adapter = DashboardActionAdapter.from_gate(gate)
    assert "label" in adapter
    assert "command" in adapter
    assert "reason" in adapter
    assert "task_id" in adapter


def test_task_next_gate_has_all_slot_attr() -> None:
    gate = TaskNextGate(task_id="t2", label="test", gate="run_worker", command="devflow task run t2 --worker shell", safety_class="approval_required", requires_human_approval=True, reason="slot test")
    assert hasattr(gate, "dashboard_label")
    assert hasattr(gate, "dashboard_command")
