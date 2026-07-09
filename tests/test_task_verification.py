from __future__ import annotations

import json
from pathlib import Path

import pytest

from devflow.legacy.control_room.persistence import get_task
from devflow.legacy.control_room.service import create_task, verify_task as service_verify_task
from devflow.legacy.control_room.task_verification import verify_task_command


def _task_path(root: Path, task_id: str) -> Path:
    return root / ".devflow" / "tasks" / task_id


def _workspace_path(root: Path, task_id: str) -> Path:
    return root / ".devflow" / "workspaces" / task_id


def _verification(root: Path, task_id: str) -> dict[str, object]:
    return json.loads((_task_path(root, task_id) / "verification.json").read_text(encoding="utf-8"))


def _event_names(root: Path, task_id: str) -> list[str]:
    return [
        json.loads(line)["event"]
        for line in (_task_path(root, task_id) / "events.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _replace_workspace(root: Path, task_id: str, workspace: str) -> None:
    yaml_path = _task_path(root, task_id) / "task.yaml"
    lines = yaml_path.read_text(encoding="utf-8").splitlines()
    updated = [f'workspace: "{workspace}"' if line.startswith("workspace:") else line for line in lines]
    yaml_path.write_text("\n".join(updated) + "\n", encoding="utf-8")


def test_verify_task_command_pass_writes_canonical_artifacts(tmp_path: Path) -> None:
    task = create_task(tmp_path, "module pass")
    (_workspace_path(tmp_path, task.id) / "ok.txt").write_text("ok\n", encoding="utf-8")

    verified = verify_task_command(tmp_path, task.id, ["/bin/sh", "-c", "test -f ok.txt && echo verified"])

    verification = _verification(tmp_path, task.id)
    assert verified.status == "verified"
    assert verified.verification_status == "passed"
    assert verified.verification_command == "/bin/sh -c 'test -f ok.txt && echo verified'"
    assert verified.verification_exit_code == 0
    assert verified.verification_log_path == f".devflow/tasks/{task.id}/logs/verify.log"
    assert verification["status"] == "passed"
    assert verification["task_status"] == "verified"
    assert verification["command"] == ["/bin/sh", "-c", "test -f ok.txt && echo verified"]
    assert (_task_path(tmp_path, task.id) / "result.md").read_text(encoding="utf-8").count("## Verification") == 1
    assert _event_names(tmp_path, task.id) == ["task_created", "verification_started", "verification_finished"]


def test_verify_task_command_fail_updates_task_and_artifacts(tmp_path: Path) -> None:
    task = create_task(tmp_path, "module fail")

    verified = verify_task_command(tmp_path, task.id, ["/bin/sh", "-c", "echo nope; exit 5"])

    verification = _verification(tmp_path, task.id)
    task_yaml = (_task_path(tmp_path, task.id) / "task.yaml").read_text(encoding="utf-8")
    assert verified.status == "verification_failed"
    assert verified.verification_status == "failed"
    assert verified.verification_exit_code == 5
    assert verification["status"] == "failed"
    assert verification["task_status"] == "verification_failed"
    assert verification["exit_code"] == 5
    assert 'status: "verification_failed"' in task_yaml
    assert 'verification_status: "failed"' in task_yaml


def test_verify_task_command_empty_command_is_rejected(tmp_path: Path) -> None:
    task = create_task(tmp_path, "module empty")

    with pytest.raises(ValueError, match="Verification requires a command after '--'\\."):
        verify_task_command(tmp_path, task.id, [])


def test_verify_task_command_refuses_destructive_command(tmp_path: Path) -> None:
    task = create_task(tmp_path, "module destructive")

    with pytest.raises(ValueError, match="Refusing obviously destructive verification command\\."):
        verify_task_command(tmp_path, task.id, ["/bin/sh", "-c", "rm -rf /"])

    assert "verification_refused" in _event_names(tmp_path, task.id)
    assert get_task(tmp_path, task.id).status == "created"


def test_verify_task_command_refuses_tampered_workspace(tmp_path: Path) -> None:
    task = create_task(tmp_path, "module tampered")
    _replace_workspace(tmp_path, task.id, ".")

    with pytest.raises(ValueError, match="Refusing unsafe task workspace"):
        verify_task_command(tmp_path, task.id, ["/bin/sh", "-c", "echo bad > main_checkout_verify.txt"])

    assert not (tmp_path / "main_checkout_verify.txt").exists()
    assert "workspace_refused" in _event_names(tmp_path, task.id)
    assert get_task(tmp_path, task.id).status == "blocked"


def test_verify_task_command_binds_to_latest_patch_application(tmp_path: Path) -> None:
    task = create_task(tmp_path, "module patch binding")
    task_path = _task_path(tmp_path, task.id)
    (task_path / "patch-application.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "task_id": task.id,
                "patch_hash": "abc123",
                "applied_at": "2026-06-25T00:00:00+00:00",
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    verified = verify_task_command(tmp_path, task.id, ["/bin/sh", "-c", "true"])

    verification = _verification(tmp_path, task.id)
    assert verified.verification_status == "passed"
    assert verification["verified_patch_hash"] == "abc123"
    assert verification["verified_patch_application_path"] == f".devflow/tasks/{task.id}/patch-application.json"
    assert verification["patch_applied_at"] == "2026-06-25T00:00:00+00:00"


def test_service_verify_task_facade_delegates_to_task_verification(tmp_path: Path) -> None:
    task = create_task(tmp_path, "service facade")
    (_workspace_path(tmp_path, task.id) / "facade.txt").write_text("ok\n", encoding="utf-8")

    verified = service_verify_task(tmp_path, task.id, ["/bin/sh", "-c", "test -f facade.txt"])

    verification = _verification(tmp_path, task.id)
    assert verified.status == "verified"
    assert verified.verification_status == "passed"
    assert verification["status"] == "passed"
    assert _event_names(tmp_path, task.id)[-2:] == ["verification_started", "verification_finished"]
