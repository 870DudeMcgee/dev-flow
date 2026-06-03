from __future__ import annotations

import json
from pathlib import Path

from devflow.control_room.worker_evidence import write_worker_evidence


def test_worker_evidence_writes_expected_structure_and_caps_raw_output(tmp_path: Path) -> None:
    evidence = write_worker_evidence(
        root=tmp_path,
        worker_type="local_model_worker_pool",
        profile_id="local-qwopus-inspector",
        worker_id="local-qwopus-inspector",
        task_id="task-0001",
        run_id="run-1",
        packet_text="packet",
        raw_output="x" * 30,
        response_text="response",
        model="qwopus:latest",
        adapter="ollama_chat",
        adapter_maturity="local_patch_runtime",
        permission_mode="read_only",
        hermes_delegable=True,
        runtime="local_model_client",
        status="success",
        started_at="2026-06-03T00:00:00+00:00",
        quality_notes="useful",
        quality_score=0.75,
        max_raw_output_chars=20,
    )

    assert evidence.evidence_dir == tmp_path / ".devflow" / "tasks" / "task-0001" / "local-model-runs" / "run-1"
    assert evidence.packet_path.read_text(encoding="utf-8") == "packet"
    assert evidence.response_path.read_text(encoding="utf-8") == "response"
    assert "raw output capped" in evidence.raw_output_path.read_text(encoding="utf-8")

    metadata = json.loads(evidence.run_metadata_path.read_text(encoding="utf-8"))
    assert metadata["worker_type"] == "local_model_worker_pool"
    assert metadata["profile_id"] == "local-qwopus-inspector"
    assert metadata["worker_id"] == "local-qwopus-inspector"
    assert metadata["task_id"] == "task-0001"
    assert metadata["run_id"] == "run-1"
    assert metadata["model"] == "qwopus:latest"
    assert metadata["adapter"] == "ollama_chat"
    assert metadata["runtime"] == "local_model_client"
    assert metadata["adapter_maturity"] == "local_patch_runtime"
    assert metadata["permission_mode"] == "read_only"
    assert metadata["hermes_delegable"] is True
    assert metadata["raw_output_capped"] is True
    assert metadata["quality_notes"] == "useful"
    assert metadata["quality_score"] == 0.75


def test_worker_evidence_failure_capture_writes_error(tmp_path: Path) -> None:
    evidence = write_worker_evidence(
        root=tmp_path,
        worker_type="local_model_worker_pool",
        profile_id="local-qwopus-inspector",
        worker_id="local-qwopus-inspector",
        task_id="task-0001",
        run_id="run-failed",
        packet_text="packet",
        raw_output="server failed",
        response_text="",
        model="qwopus:latest",
        adapter="ollama_chat",
        adapter_maturity="local_patch_runtime",
        permission_mode="read_only",
        hermes_delegable=True,
        runtime="local_model_client",
        status="failed",
        started_at="2026-06-03T00:00:00+00:00",
        error_message="server failed",
    )

    assert evidence.error_path.read_text(encoding="utf-8") == "server failed"
    metadata = json.loads(evidence.run_metadata_path.read_text(encoding="utf-8"))
    assert metadata["status"] == "failed"
    assert metadata["failure_captured"] is True
    assert metadata["error_message"] == "server failed"
