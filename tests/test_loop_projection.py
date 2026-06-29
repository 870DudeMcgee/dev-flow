from devflow.control_room.loops import loop_artifact, loop_envelope, loop_phase, status_label


def test_status_label_normalizes_separators() -> None:
    assert status_label("stopped_needs-review") == "Stopped Needs Review"


def test_loop_envelope_uses_empty_defaults() -> None:
    envelope = loop_envelope(loop_family="refactor", run_id="run-1", status="stopped_needs_review")

    assert envelope["status_label"] == "Stopped Needs Review"
    assert envelope["phases"] == []
    assert envelope["artifacts"] == []
    assert envelope["evidence_path"] is None
    assert envelope["next_safe_action"] == ""
    assert "loop_id" not in envelope


def test_loop_envelope_preserves_extra_fields() -> None:
    envelope = loop_envelope(
        loop_family="builder_judge",
        run_id="run-2",
        status="running",
        extra={"custom": 7, "status": "shadow"},
    )

    assert envelope["custom"] == 7
    assert envelope["status"] == "running"


def test_loop_envelope_common_fields_override_extra() -> None:
    envelope = loop_envelope(
        loop_family="builder_judge",
        run_id="run-3",
        status="blocked",
        loop_id="loop-3",
        status_label="Blocked",
        phases=[loop_phase("plan", "done", "ready")],
        artifacts=[loop_artifact("Log", "log", None, False)],
        evidence_path="/tmp/evidence.json",
        next_safe_action="Inspect logs",
        extra={
            "loop_family": "refactor",
            "run_id": "shadow",
            "status": "shadow",
            "loop_id": "shadow",
            "status_label": "shadow",
            "phases": [{"name": "shadow", "state": "shadow", "detail": "shadow"}],
            "artifacts": [{"label": "shadow", "kind": "shadow", "path": "shadow", "exists": True}],
            "evidence_path": "shadow",
            "next_safe_action": "shadow",
        },
    )

    assert envelope == {
        "loop_family": "builder_judge",
        "run_id": "run-3",
        "status": "blocked",
        "loop_id": "loop-3",
        "status_label": "Blocked",
        "phases": [{"name": "plan", "state": "done", "detail": "ready"}],
        "artifacts": [{"label": "Log", "kind": "log", "path": None, "exists": False}],
        "evidence_path": "/tmp/evidence.json",
        "next_safe_action": "Inspect logs",
    }
