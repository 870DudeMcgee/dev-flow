from __future__ import annotations

import json
import threading
from http.client import HTTPConnection
from pathlib import Path
from typing import Any

import pytest

from devflow.control_room.architecture_audit import (
    ArchitectureAuditResult,
    DiagnosticStatus,
    GraphMetrics,
    GraphifyStatus,
)
from devflow.control_room.refactor_loop import (
    REFACTOR_APPROVAL_ACTION,
    RefactorLoopError,
    load_refactor_run_status,
    persist_refactor_run_result,
    require_refactor_approval,
    start_refactor_loop,
)


def _audit(issue_count: int | None, *, target: str = "src/devflow/control_room/service.py") -> ArchitectureAuditResult:
    return ArchitectureAuditResult(
        graphify=GraphifyStatus(available=True, path="/tmp/graphify", install_status="not_requested"),
        graph_metrics=GraphMetrics(nodes=10, edges=20, communities=2),
        diagnostic=DiagnosticStatus(status="issues", issue_count=issue_count, raw={"issue_count": issue_count}),
        recommended_cleanup_targets=[target],
    )


def _approval(worker: str = "codex55") -> dict[str, object]:
    return {
        "worker": worker,
        "human_approved": True,
        "approval_phrase": "I approve this exact Dev-Flow command",
        "approved_action": REFACTOR_APPROVAL_ACTION,
        "approved_worker": worker,
    }


def _hermes_sessions(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    hermes_home = home / ".hermes"
    sessions = hermes_home / "sessions"
    sessions.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HOME", home.as_posix())
    monkeypatch.setenv("HERMES_HOME", hermes_home.as_posix())
    return sessions


def test_refactor_loop_starts_with_exact_issue_count_and_selected_worker(tmp_path: Path) -> None:
    calls: dict[str, Any] = {}
    scorecard = tmp_path / ".devflow" / "architecture-rehab" / "scorecards" / "score.json"

    def fake_loop(root: Path, worker: str, max_iterations: int, scorecard_path: Path, candidate: str) -> dict[str, Any]:
        calls.update(
            root=root,
            worker=worker,
            max_iterations=max_iterations,
            scorecard_path=scorecard_path,
            candidate=candidate,
        )
        return {
            "started": True,
            "returncode": 0,
            "goal_file": ".devflow/architecture-rehab/goals/rehab.md",
            "loop_log": "/tmp/loop.log",
            "loop_pid": "/tmp/loop.pid",
            "command": ["/Users/josh/Desktop/Loop Goal Script/loop.py", "start"],
            "profile": "dfcodex55",
            "planner_profile": "dfcodex55",
            "judge_profile": "dfcodex55",
        }

    result = start_refactor_loop(
        tmp_path,
        worker="codex55",
        audit_runner=lambda root: _audit(3),
        scorecard_writer=lambda root: scorecard,
        loop_starter=fake_loop,
    )

    assert result["started"] is True
    assert result["issue_count"] == 3
    assert result["worker"] == "codex55"
    assert result["scorecard_path"] == scorecard.as_posix()
    assert result["run_id"].startswith("refactor-")
    assert result["run_path"].endswith(f"{result['run_id']}.json")
    assert result["profile"] == "dfcodex55"
    assert result["planner_profile"] == "dfcodex55"
    assert result["judge_profile"] == "dfcodex55"
    assert calls["max_iterations"] == 3
    assert calls["worker"] == "codex55"
    assert "Use Graphify evidence" in calls["candidate"]
    assert "Ponytail simplification ladder" in calls["candidate"]
    assert "skip unnecessary work" in calls["candidate"]


def test_refactor_run_status_projects_profiles_artifacts_and_sanitized_log_tail(tmp_path: Path) -> None:
    scorecard = tmp_path / ".devflow" / "architecture-rehab" / "scorecards" / "score.json"
    scorecard.parent.mkdir(parents=True, exist_ok=True)
    scorecard.write_text('{"verdict": "pass"}\n', encoding="utf-8")
    log_path = tmp_path / ".devflow" / "architecture-rehab" / "logs" / "loop.log"
    pid_path = tmp_path / ".devflow" / "architecture-rehab" / "logs" / "loop.pid"

    def fake_loop(root: Path, worker: str, max_iterations: int, scorecard_path: Path, candidate: str) -> dict[str, Any]:
        return {
            "started": True,
            "returncode": 0,
            "goal_file": ".devflow/architecture-rehab/goals/rehab.md",
            "loop_log": log_path.as_posix(),
            "loop_pid": pid_path.as_posix(),
            "loop_slug": "graphify-rehab-loop",
            "command": ["loop.py", "start", "--background"],
            "profile": "dfcodex55",
            "planner_profile": "dfcodex55",
            "planner_toolsets": "terminal",
            "judge_profile": "dfcodex55",
            "preflight": {"ok": True, "model": "codex"},
            "planner_preflight": {"ok": True, "model": "codex"},
            "judge_preflight": {"ok": True, "model": "codex"},
        }

    result = start_refactor_loop(
        tmp_path,
        worker="codex55",
        audit_runner=lambda root: _audit(2),
        scorecard_writer=lambda root: scorecard,
        loop_starter=fake_loop,
    )
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(
        "\x1b[31mPlanner rationale recorded\x1b[0m\n"
        "Worker output: split a focused module\n"
        "Judge feedback: handoff accepted\n"
        "Completed handoff with next safe action\n",
        encoding="utf-8",
    )

    status = load_refactor_run_status(tmp_path, run_id=result["run_id"])

    assert status["run_id"] == result["run_id"]
    assert status["loop_family"] == "refactor"
    assert status["run_path"] == result["run_path"]
    assert status["evidence_path"] == result["run_path"]
    assert status["status"] == "completed"
    assert status["worker"] == "codex55"
    assert status["profile"] == "dfcodex55"
    assert status["planner_profile"] == "dfcodex55"
    assert status["judge_profile"] == "dfcodex55"
    assert status["log_tail"][-1] == "Completed handoff with next safe action"
    assert all("\x1b" not in line for line in status["log_tail"])
    assert [phase["name"] for phase in status["phases"]] == [
        "Graphify audit",
        "Scorecard",
        "Goal file",
        "Planner",
        "Worker",
        "Judge",
        "Handoff",
    ]
    assert any(item["path"] == scorecard.as_posix() and item["exists"] for item in status["artifacts"])


def test_refactor_run_status_projects_handoff_plan_and_paused_resume_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sessions = _hermes_sessions(tmp_path, monkeypatch)
    slug = "graphify-rehab-loop"
    (sessions / f"worker-plan-{slug}-iter-1.md").write_text(
        "# Worker Plan\n\nCurrent Small Fix: keep one safe architecture slice.\n",
        encoding="utf-8",
    )
    (sessions / f"handoff-{slug}.md").write_text(
        "## Blockers / Decisions\nShutdown by signal.\n\n"
        "## Next Action\nResume: loop resume graphify-rehab-loop\n",
        encoding="utf-8",
    )
    log_path = tmp_path / ".devflow" / "architecture-rehab" / "logs" / "loop.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text("Shutdown requested during session\nLoop ended\n", encoding="utf-8")
    result = persist_refactor_run_result(
        tmp_path,
        {
            "started": True,
            "issue_count": 2,
            "worker": "codex55",
            "profile": "dfcodex55",
            "planner_profile": "dfcodex55",
            "judge_profile": "dfcodex55",
            "loop_slug": slug,
            "loop_log": log_path.as_posix(),
        },
    )

    status = load_refactor_run_status(tmp_path, run_id=result["run_id"])

    assert status["loop_family"] == "refactor"
    assert status["evidence_path"] == result["run_path"]
    assert status["status"] == "paused"
    assert status["status_source"] == "handoff"
    assert "Shutdown by signal" in status["status_reason"]
    assert status["planner_evidence"]["path"].endswith(f"worker-plan-{slug}-iter-1.md")
    assert "Current Small Fix" in "\n".join(status["planner_evidence"]["tail"])
    assert status["handoff_evidence"]["next_action"] == "Resume: loop resume graphify-rehab-loop"
    artifact_kinds = {item["kind"] for item in status["artifacts"]}
    assert {"planner", "handoff"} <= artifact_kinds


def test_refactor_run_status_blocks_on_planner_failure_handoff(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sessions = _hermes_sessions(tmp_path, monkeypatch)
    slug = "planner-blocked-loop"
    (sessions / f"handoff-{slug}.md").write_text(
        "## Blockers / Decisions\nplanner profile dfcodex55 returned no worker plan\n\n"
        "## Errors\nplanner profile dfcodex55 returned no worker plan\n\n"
        "## Next Action\nFix planner/profile output; do not start worker without a plan.\n",
        encoding="utf-8",
    )
    result = persist_refactor_run_result(
        tmp_path,
        {
            "started": True,
            "issue_count": 1,
            "worker": "codex55",
            "profile": "dfcodex55",
            "planner_profile": "dfcodex55",
            "judge_profile": "dfcodex55",
            "loop_slug": slug,
        },
    )

    status = load_refactor_run_status(tmp_path, run_id=result["run_id"])

    assert status["status"] == "blocked"
    assert status["status_source"] == "handoff"
    assert "no worker plan" in status["status_reason"]
    assert status["judge_evidence"]["blocker"] == "planner profile dfcodex55 returned no worker plan"
    assert status["next_safe_action"] == "Fix planner/profile output; do not start worker without a plan."


def test_refactor_run_status_uses_loop_status_for_stopped_needs_review(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    slug = "needs-review-loop"
    monkeypatch.setattr(
        "devflow.control_room.refactor_loop._collect_loop_status_snapshot",
        lambda root, record: {
            "loop_status": {
                "returncode": 0,
                "stdout": "SLUG ITER STATUS NEXT ACTION\nneeds-review-loop 1 stopped Inspect the latest handoff",
                "stderr": "",
            },
            "watch": {"returncode": 0, "stdout": "needs-review-loop stopped", "stderr": ""},
        },
        raising=False,
    )
    result = persist_refactor_run_result(
        tmp_path,
        {
            "started": True,
            "issue_count": 1,
            "worker": "local-fast",
            "profile": "dflocalfast",
            "loop_slug": slug,
        },
    )

    status = load_refactor_run_status(tmp_path, run_id=result["run_id"])

    assert status["status"] == "stopped_needs_review"
    assert status["status_source"] == "loop_status"
    assert "Inspect the latest handoff" in status["status_reason"]
    assert "needs-review-loop" in status["loop_evidence"]["loop_status"]["stdout"]


def test_refactor_run_status_keeps_completed_when_watch_has_no_loop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    slug = "completed-loop"
    monkeypatch.setattr(
        "devflow.control_room.refactor_loop._collect_loop_status_snapshot",
        lambda root, record: {
            "loop_status": {
                "returncode": 0,
                "stdout": "SLUG ITER STATUS NEXT ACTION\nother-loop 1 stopped Resolve the worker/provider error shown",
                "stderr": "",
            },
            "watch": {"returncode": 0, "stdout": "No loop found matching 'completed-loop'", "stderr": ""},
        },
        raising=False,
    )
    log_path = tmp_path / ".devflow" / "architecture-rehab" / "logs" / "loop.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text("Worker output\nCompleted handoff with next safe action\n", encoding="utf-8")
    result = persist_refactor_run_result(
        tmp_path,
        {
            "started": True,
            "issue_count": 1,
            "worker": "codex55",
            "profile": "dfcodex55",
            "loop_slug": slug,
            "loop_log": log_path.as_posix(),
        },
    )

    status = load_refactor_run_status(tmp_path, run_id=result["run_id"])

    assert status["status"] == "completed"
    assert status["status_source"] == "log"
    assert "No loop found" in status["loop_evidence"]["watch"]["stdout"]


def test_refactor_run_status_rejects_invalid_run_id(tmp_path: Path) -> None:
    with pytest.raises(RefactorLoopError, match="run_id"):
        load_refactor_run_status(tmp_path, run_id="../secret")


def test_refactor_loop_zero_issues_does_not_start(tmp_path: Path) -> None:
    def fail_loop(*_: object) -> dict[str, Any]:
        raise AssertionError("loop should not start")

    result = start_refactor_loop(
        tmp_path,
        worker="local-fast",
        audit_runner=lambda root: _audit(0),
        scorecard_writer=lambda root: tmp_path / "score.json",
        loop_starter=fail_loop,
    )

    assert result["started"] is False
    assert result["issue_count"] == 0
    assert result["error"] is None
    assert "No refactor issues" in result["message"]


def test_refactor_loop_missing_issue_count_returns_repair_error(tmp_path: Path) -> None:
    result = start_refactor_loop(
        tmp_path,
        worker="local-fast",
        audit_runner=lambda root: _audit(None),
        scorecard_writer=lambda root: tmp_path / "score.json",
        loop_starter=lambda *_: {"started": True},
    )

    assert result["started"] is False
    assert result["exit_code"] == 1
    assert "issue_count" in result["error"]


def test_refactor_loop_rejects_invalid_worker_before_audit(tmp_path: Path) -> None:
    with pytest.raises(RefactorLoopError, match="worker must be one of"):
        start_refactor_loop(
            tmp_path,
            worker="space-cadet",
            audit_runner=lambda root: (_ for _ in ()).throw(AssertionError("audit should not run")),
        )


def test_refactor_approval_requires_exact_action_and_worker() -> None:
    require_refactor_approval(_approval("local-fast"))

    bad = _approval("codex55")
    bad["approved_worker"] = "local-fast"
    with pytest.raises(RefactorLoopError, match="approved_worker"):
        require_refactor_approval(bad)

    missing = _approval("codex55")
    missing["human_approved"] = False
    with pytest.raises(RefactorLoopError, match="human approval"):
        require_refactor_approval(missing)


def test_operating_layer_refactor_endpoint_blocks_unapproved_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from devflow.control_room.operating_layer_server import OperatingLayerHTTPServer

    calls: list[tuple[Path, str]] = []

    def fake_start(root: Path, *, worker: str) -> dict[str, object]:
        calls.append((root, worker))
        return {"started": True, "issue_count": 2, "worker": worker, "error": None}

    monkeypatch.setattr("devflow.control_room.operating_layer_server.start_refactor_loop", fake_start)
    server = OperatingLayerHTTPServer(("127.0.0.1", 0), tmp_path)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address

    try:
        conn = HTTPConnection(host, port, timeout=5)
        conn.request(
            "POST",
            "/api/refactor/start",
            body=json.dumps({"worker": "codex55"}),
            headers={"Content-Type": "application/json"},
        )
        blocked = conn.getresponse()
        assert blocked.status == 400
        assert calls == []

        conn = HTTPConnection(host, port, timeout=5)
        conn.request(
            "POST",
            "/api/refactor/start",
            body=json.dumps(_approval("codex55")),
            headers={"Content-Type": "application/json"},
        )
        response = conn.getresponse()
        payload = json.loads(response.read().decode("utf-8"))
        assert response.status == 200
        assert payload["started"] is True
        assert calls == [(tmp_path.resolve(), "codex55")]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_operating_layer_refactor_status_endpoint_reads_persisted_run(
    tmp_path: Path,
) -> None:
    from devflow.control_room.operating_layer_server import OperatingLayerHTTPServer

    log_path = tmp_path / ".devflow" / "architecture-rehab" / "logs" / "loop.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text("Worker output line\nCompleted handoff\n", encoding="utf-8")
    result = persist_refactor_run_result(
        tmp_path,
        {
            "started": True,
            "issue_count": 1,
            "worker": "local-fast",
            "profile": "dflocalfast",
            "planner_profile": "dfcodex55",
            "judge_profile": "dfcodex55",
            "loop_log": log_path.as_posix(),
            "loop_slug": "persisted-loop",
            "command": ["loop.py", "start"],
        },
    )

    server = OperatingLayerHTTPServer(("127.0.0.1", 0), tmp_path)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address

    try:
        conn = HTTPConnection(host, port, timeout=5)
        conn.request("GET", f"/api/refactor/status?run_id={result['run_id']}")
        response = conn.getresponse()
        payload = json.loads(response.read().decode("utf-8"))
        assert response.status == 200
        assert payload["run_id"] == result["run_id"]
        assert payload["loop_family"] == "refactor"
        assert payload["run_path"] == result["run_path"]
        assert payload["evidence_path"] == result["run_path"]
        assert payload["status"] == "completed"
        assert payload["log_tail"][-1] == "Completed handoff"
        assert payload["status_reason"]
        assert "loop_evidence" in payload
        assert "planner_evidence" in payload
        assert "handoff_evidence" in payload
        assert "judge_evidence" in payload

        conn = HTTPConnection(host, port, timeout=5)
        conn.request("GET", "/api/refactor/status?run_id=../secret")
        blocked = conn.getresponse()
        assert blocked.status == 400
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
