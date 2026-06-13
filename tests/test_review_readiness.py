from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from devflow.cli import app
from devflow.control_room.persistence import get_task, save_task, utc_now


runner = CliRunner()


def _write_promotion_preview(
    root: Path,
    task_id: str,
    readiness: str = "ready",
    *,
    preview_task_id: str | None = None,
) -> None:
    path = root / ".devflow" / "tasks" / task_id / "promotion-preview.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "task_id": preview_task_id or task_id,
                "promotion_readiness": readiness,
                "human_approval_required": False,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _write_default_promotion_preview_without_readiness(root: Path, task_id: str) -> None:
    path = root / ".devflow" / "tasks" / task_id / "promotion-preview.json"
    path.write_text(
        json.dumps(
            {
                "task_id": task_id,
                "baseline": {"baseline_status": "unavailable"},
                "added": [],
                "modified": [],
                "deleted": [],
                "diffs": {},
                "human_approval": {"required": False},
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _task_file_snapshot(root: Path, task_id: str) -> dict[str, bytes]:
    base = root / ".devflow" / "tasks" / task_id
    return {
        path.relative_to(base).as_posix(): path.read_bytes()
        for path in sorted(base.rglob("*"))
        if path.is_file()
    }


def _set_task_state(
    root: Path,
    task_id: str,
    *,
    status: str,
    verification_status: str = "not_run",
    verification_exit_code: int | None = None,
) -> None:
    task = get_task(root, task_id)
    task.status = status
    task.verification_status = verification_status
    task.verification_exit_code = verification_exit_code
    task.updated_at = utc_now()
    save_task(root / ".devflow" / "tasks" / task_id, task)


def test_review_ready_cli_reports_ready_for_review_and_is_read_only(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    assert runner.invoke(app, ["task", "create", "ready review"]).exit_code == 0
    run = runner.invoke(
        app,
        ["task", "run", "task-0001", "--worker", "shell", "--", "/bin/sh", "-c", "echo ready > result.txt"],
    )
    assert run.exit_code == 0, run.output
    verify = runner.invoke(app, ["task", "verify", "task-0001", "--shell", "test -f result.txt"])
    assert verify.exit_code == 0, verify.output
    preview = runner.invoke(app, ["task", "promote-preview", "task-0001"])
    assert preview.exit_code == 0, preview.output

    before = _task_file_snapshot(tmp_path, "task-0001")
    result = runner.invoke(app, ["task", "review-ready", "task-0001", "--json"])
    after = _task_file_snapshot(tmp_path, "task-0001")

    assert result.exit_code == 0, result.output
    assert before == after
    payload = json.loads(result.output)
    assert payload["task_id"] == "task-0001"
    assert payload["review_state"] == "ready_for_review"
    assert payload["score"] == 100
    assert payload["blockers"] == []
    assert payload["next_command"] == "devflow task capsule task-0001"
    assert ".devflow/tasks/task-0001/task.yaml" in payload["evidence"]
    assert ".devflow/tasks/task-0001/verification.json" in payload["evidence"]
    assert ".devflow/tasks/task-0001/promotion-preview.json" in payload["evidence"]


def test_review_ready_cli_reports_needs_verification_for_completed_worker_output(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    assert runner.invoke(app, ["task", "create", "needs verify"]).exit_code == 0
    run = runner.invoke(app, ["task", "run", "task-0001", "--shell", "echo done > result.txt"])
    assert run.exit_code == 0, run.output

    result = runner.invoke(app, ["task", "review-ready", "task-0001", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["review_state"] == "needs_verification"
    assert payload["score"] == 60
    assert payload["blockers"] == ["verification has not passed"]
    assert payload["next_command"] == 'devflow task verify task-0001 --shell "<command>"'


def test_review_ready_cli_reports_verification_failed(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    assert runner.invoke(app, ["task", "create", "failed verify"]).exit_code == 0
    assert runner.invoke(app, ["task", "run", "task-0001", "--shell", "echo done > result.txt"]).exit_code == 0
    verify = runner.invoke(app, ["task", "verify", "task-0001", "--shell", "exit 7"])
    assert verify.exit_code == 7, verify.output

    result = runner.invoke(app, ["task", "review-ready", "task-0001", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["review_state"] == "verification_failed"
    assert payload["score"] == 40
    assert payload["blockers"] == ["verification failed"]
    assert payload["next_command"] == "devflow task log task-0001 --verify --tail 80"


def test_review_ready_cli_reports_needs_promotion_preview(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    assert runner.invoke(app, ["task", "create", "preview missing"]).exit_code == 0
    assert runner.invoke(app, ["task", "run", "task-0001", "--shell", "echo done > result.txt"]).exit_code == 0
    verify = runner.invoke(app, ["task", "verify", "task-0001", "--shell", "test -f result.txt"])
    assert verify.exit_code == 0, verify.output

    result = runner.invoke(app, ["task", "review-ready", "task-0001", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["review_state"] == "needs_promotion_preview"
    assert payload["score"] == 80
    assert payload["blockers"] == ["promotion-preview.json is missing"]
    assert payload["next_command"] == "devflow task promote-preview task-0001"


def test_review_ready_rejects_non_ready_git_native_preview(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    assert runner.invoke(app, ["task", "create", "preview not ready"]).exit_code == 0
    assert runner.invoke(app, ["task", "run", "task-0001", "--shell", "echo done > result.txt"]).exit_code == 0
    verify = runner.invoke(app, ["task", "verify", "task-0001", "--shell", "test -f result.txt"])
    assert verify.exit_code == 0, verify.output
    _write_promotion_preview(tmp_path, "task-0001", readiness="blocked")

    result = runner.invoke(app, ["task", "review-ready", "task-0001", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["review_state"] == "needs_promotion_preview"
    assert payload["score"] == 80
    assert payload["blockers"] == ["promotion preview is not ready: blocked"]


def test_review_ready_rejects_preview_for_wrong_task(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    assert runner.invoke(app, ["task", "create", "wrong task"]).exit_code == 0
    assert runner.invoke(app, ["task", "run", "task-0001", "--shell", "echo done > result.txt"]).exit_code == 0
    verify = runner.invoke(app, ["task", "verify", "task-0001", "--shell", "test -f result.txt"])
    assert verify.exit_code == 0, verify.output
    _write_promotion_preview(tmp_path, "task-0001", preview_task_id="task-9999")

    result = runner.invoke(app, ["task", "review-ready", "task-0001", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["review_state"] == "needs_promotion_preview"
    assert payload["score"] == 80
    assert payload["blockers"] == ["promotion-preview.json task_id is 'task-9999', expected 'task-0001'"]


def test_review_ready_rejects_invalid_verification_json_even_with_ready_preview(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    assert runner.invoke(app, ["task", "create", "corrupt verification"]).exit_code == 0
    assert runner.invoke(app, ["task", "run", "task-0001", "--shell", "echo done > result.txt"]).exit_code == 0
    verify = runner.invoke(app, ["task", "verify", "task-0001", "--shell", "test -f result.txt"])
    assert verify.exit_code == 0, verify.output
    preview = runner.invoke(app, ["task", "promote-preview", "task-0001"])
    assert preview.exit_code == 0, preview.output
    (tmp_path / ".devflow" / "tasks" / "task-0001" / "verification.json").write_text(
        "{not-json\n",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["task", "review-ready", "task-0001", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["review_state"] == "needs_verification"
    assert payload["score"] == 60
    assert payload["blockers"] == ["verification.json is invalid JSON: Expecting property name enclosed in double quotes"]
    assert payload["next_command"] == 'devflow task verify task-0001 --shell "<command>"'


def test_review_ready_rejects_stale_patch_verification_binding(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    assert runner.invoke(app, ["task", "create", "stale patch verification"]).exit_code == 0
    assert runner.invoke(app, ["task", "run", "task-0001", "--shell", "echo done > result.txt"]).exit_code == 0
    verify = runner.invoke(app, ["task", "verify", "task-0001", "--shell", "test -f result.txt"])
    assert verify.exit_code == 0, verify.output
    preview = runner.invoke(app, ["task", "promote-preview", "task-0001"])
    assert preview.exit_code == 0, preview.output
    (tmp_path / ".devflow" / "tasks" / "task-0001" / "patch-application.json").write_text(
        json.dumps({"patch_hash": "newer-patch-hash"}) + "\n",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["task", "review-ready", "task-0001", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["review_state"] == "needs_verification"
    assert payload["score"] == 60
    assert "verification.json verified_patch_hash is missing for latest patch application" in payload["blockers"]
    assert (
        "verification.json verified_patch_application_path is missing for latest patch application"
        in payload["blockers"]
    )


def test_review_ready_cli_reports_blocked_worker_failed_and_running_states(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    assert runner.invoke(app, ["task", "create", "blocked"]).exit_code == 0
    assert runner.invoke(app, ["task", "create", "worker failed"]).exit_code == 0
    assert runner.invoke(app, ["task", "create", "running"]).exit_code == 0
    _set_task_state(tmp_path, "task-0001", status="blocked")
    _set_task_state(tmp_path, "task-0002", status="worker_failed")
    _set_task_state(tmp_path, "task-0003", status="running", verification_status="pending")

    result = runner.invoke(app, ["task", "review-ready", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    states = {item["task_id"]: item["review_state"] for item in payload["tasks"]}
    assert states == {
        "task-0001": "blocked",
        "task-0002": "worker_failed",
        "task-0003": "running",
    }


def test_review_ready_project_scope_and_capsule_project_option_are_runnable(
    tmp_path: Path,
    monkeypatch,
) -> None:
    projects_root = tmp_path / "projects"
    monkeypatch.setenv("DEVFLOW_PROJECTS_ROOT", projects_root.as_posix())
    monkeypatch.setenv("DEVFLOW_HOME", (tmp_path / "home" / ".devflow").as_posix())
    monkeypatch.chdir(tmp_path)

    created = runner.invoke(app, ["project", "create", "Demo App", "--projects-root", projects_root.as_posix()])
    assert created.exit_code == 0, created.output
    project_root = projects_root / "demo-app"
    assert project_root.exists()
    monkeypatch.chdir(project_root)
    baseline = runner.invoke(app, ["git", "checkpoint", "--message", "project baseline", "--yes"])
    assert baseline.exit_code == 0, baseline.output
    monkeypatch.chdir(tmp_path)

    task_created = runner.invoke(app, ["task", "create", "--project", "demo-app", "project ready"])
    assert task_created.exit_code == 0, task_created.output
    run = runner.invoke(app, ["task", "run", "task-0001", "--project", "demo-app", "--shell", "echo done > result.txt"])
    assert run.exit_code == 0, run.output
    verify = runner.invoke(app, ["task", "verify", "task-0001", "--project", "demo-app", "--shell", "test -f result.txt"])
    assert verify.exit_code == 0, verify.output
    preview = runner.invoke(app, ["task", "promote-preview", "task-0001", "--project", "demo-app"])
    assert preview.exit_code == 0, preview.output

    result = runner.invoke(app, ["task", "review-ready", "task-0001", "--project", "demo-app", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["next_command"] == "devflow task capsule task-0001 --project demo-app"

    capsule = runner.invoke(app, ["task", "capsule", "task-0001", "--project", "demo-app"])
    assert capsule.exit_code == 0, capsule.output
    assert "REVIEW CAPSULE - task-0001" in capsule.output


def test_review_ready_accepts_default_promotion_preview_schema_without_readiness(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    assert runner.invoke(app, ["task", "create", "default preview"]).exit_code == 0
    assert runner.invoke(app, ["task", "run", "task-0001", "--shell", "echo done > result.txt"]).exit_code == 0
    verify = runner.invoke(app, ["task", "verify", "task-0001", "--shell", "test -f result.txt"])
    assert verify.exit_code == 0, verify.output
    _write_default_promotion_preview_without_readiness(tmp_path, "task-0001")

    result = runner.invoke(app, ["task", "review-ready", "task-0001", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["review_state"] == "ready_for_review"
    assert payload["score"] == 100
    assert payload["blockers"] == []


def test_review_ready_rejects_missing_readiness_without_default_preview_schema(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    assert runner.invoke(app, ["task", "create", "bad preview"]).exit_code == 0
    assert runner.invoke(app, ["task", "run", "task-0001", "--shell", "echo done > result.txt"]).exit_code == 0
    verify = runner.invoke(app, ["task", "verify", "task-0001", "--shell", "test -f result.txt"])
    assert verify.exit_code == 0, verify.output
    path = tmp_path / ".devflow" / "tasks" / "task-0001" / "promotion-preview.json"
    path.write_text(json.dumps({"task_id": "task-0001", "baseline": {}}) + "\n", encoding="utf-8")

    result = runner.invoke(app, ["task", "review-ready", "task-0001", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["review_state"] == "needs_promotion_preview"
    assert payload["score"] == 80
    assert payload["blockers"] == ["promotion-preview.json promotion_readiness is missing"]
