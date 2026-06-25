from __future__ import annotations

import json
from pathlib import Path

import pytest

from devflow.control_room.patch_applier import PatchApplicationError, PatchSelectionError
from devflow.control_room.service import apply_task_patch as service_apply_task_patch
from devflow.control_room.service import create_task
from devflow.control_room.task_patch_application import apply_task_patch_command


def _task_path(root: Path, task_id: str) -> Path:
    return root / ".devflow" / "tasks" / task_id


def _workspace_path(root: Path, task_id: str) -> Path:
    return root / ".devflow" / "workspaces" / task_id


def _modify_patch(path: str, old: str, new: str) -> str:
    return (
        f"--- a/{path}\n"
        f"+++ b/{path}\n"
        "@@ -1 +1 @@\n"
        f"-{old}\n"
        f"+{new}\n"
    )


def _write_agent_patch(root: Path, task_id: str, agent_id: str, patch: str) -> Path:
    agent_dir = _task_path(root, task_id) / "agents" / agent_id
    agent_dir.mkdir(parents=True, exist_ok=True)
    patch_path = agent_dir / "proposal.patch"
    patch_path.write_text(patch, encoding="utf-8")
    return patch_path


def _write_reviewed_dry_run(
    root: Path,
    task_id: str,
    patch: str,
    *,
    run_id: str = "run-1",
    review_status: str = "low_risk_candidate",
    dry_run_status: str = "would_apply_cleanly",
) -> Path:
    run_path = _task_path(root, task_id) / "local-model-runs" / run_id
    run_path.mkdir(parents=True, exist_ok=True)
    patch_path = run_path / "proposal.patch"
    patch_path.write_text(patch, encoding="utf-8")
    patch_rel = f".devflow/tasks/{task_id}/local-model-runs/{run_id}/proposal.patch"
    review_rel = f".devflow/tasks/{task_id}/local-model-runs/{run_id}/patch-review.json"
    (run_path / "patch-review.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "task_id": task_id,
                "run_id": run_id,
                "patch_path": patch_rel,
                "review_status": review_status,
                "risk": "low",
                "files_touched": ["hello.txt"],
                "hunk_count": 1,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (run_path / "patch-dry-run.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "task_id": task_id,
                "run_id": run_id,
                "proposal_patch_path": patch_rel,
                "patch_review_path": review_rel,
                "workspace_path": f".devflow/workspaces/{task_id}",
                "dry_run_status": dry_run_status,
                "risk": "low",
                "files_checked": ["hello.txt"],
                "files_missing": [],
                "files_would_create": [],
                "files_would_modify": ["hello.txt"],
                "files_would_delete": [],
                "hunks_checked": 1,
                "hunks_matched": 1,
                "hunks_failed": 0,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return run_path


def _patch_application(root: Path, task_id: str) -> dict[str, object]:
    return json.loads((_task_path(root, task_id) / "patch-application.json").read_text(encoding="utf-8"))


def _patch_events(root: Path, task_id: str) -> list[dict[str, object]]:
    events_path = _task_path(root, task_id) / "events.jsonl"
    return [
        json.loads(line)
        for line in events_path.read_text(encoding="utf-8").splitlines()
        if line.strip() and json.loads(line).get("event") == "patch_applied"
    ]


def test_apply_task_patch_command_applies_reviewed_agent_patch(tmp_path: Path) -> None:
    task = create_task(tmp_path, "module agent apply")
    hello_file = _workspace_path(tmp_path, task.id) / "hello.txt"
    hello_file.write_text("Hello World\n", encoding="utf-8")
    patch = _modify_patch("hello.txt", "Hello World", "Hello module agent")
    _write_agent_patch(tmp_path, task.id, "agent-a", patch)
    _write_reviewed_dry_run(tmp_path, task.id, patch, run_id="agent-agent-a")

    updated = apply_task_patch_command(tmp_path, task.id, agent_id="agent-a")

    evidence = _patch_application(tmp_path, task.id)
    events = _patch_events(tmp_path, task.id)
    assert updated.status == "complete"
    assert hello_file.read_text(encoding="utf-8") == "Hello module agent\n"
    assert evidence["agent_id"] == "agent-a"
    assert evidence["run_id"] == "agent-agent-a"
    assert evidence["patch_path"] == f".devflow/tasks/{task.id}/agents/agent-a/proposal.patch"
    assert evidence["changed_files"] == [
        {"path": "hello.txt", "operation": "modified", "additions": 1, "deletions": 1}
    ]
    assert events[-1]["patch_hash"] == evidence["patch_hash"]
    assert events[-1]["patch_evidence_path"] == f".devflow/tasks/{task.id}/patches/{evidence['patch_hash']}.json"


def test_apply_task_patch_command_applies_reviewed_local_run_patch(tmp_path: Path) -> None:
    task = create_task(tmp_path, "module local run apply")
    hello_file = _workspace_path(tmp_path, task.id) / "hello.txt"
    hello_file.write_text("Hello World\n", encoding="utf-8")
    patch = _modify_patch("hello.txt", "Hello World", "Hello module run")
    _write_reviewed_dry_run(tmp_path, task.id, patch, run_id="run-apply")

    updated = apply_task_patch_command(tmp_path, task.id, run_id="run-apply")

    evidence = _patch_application(tmp_path, task.id)
    assert updated.id == task.id
    assert hello_file.read_text(encoding="utf-8") == "Hello module run\n"
    assert evidence["agent_id"] is None
    assert evidence["run_id"] == "run-apply"
    assert evidence["patch_path"] == f".devflow/tasks/{task.id}/local-model-runs/run-apply/proposal.patch"


def test_apply_task_patch_command_refuses_multiple_agent_patches(tmp_path: Path) -> None:
    task = create_task(tmp_path, "module multiple patches")
    _write_agent_patch(tmp_path, task.id, "agent-a", _modify_patch("hello.txt", "old", "new-a"))
    _write_agent_patch(tmp_path, task.id, "agent-b", _modify_patch("hello.txt", "old", "new-b"))

    with pytest.raises(PatchSelectionError) as excinfo:
        apply_task_patch_command(tmp_path, task.id)
    message = str(excinfo.value)
    assert "Multiple proposal patches found:" in message
    assert "'agent-a'" in message
    assert "'agent-b'" in message
    assert "Please specify which one to apply using --agent." in message


def test_apply_task_patch_command_refuses_missing_gate_without_mutation(tmp_path: Path) -> None:
    task = create_task(tmp_path, "module missing gate")
    hello_file = _workspace_path(tmp_path, task.id) / "hello.txt"
    hello_file.write_text("Hello World\n", encoding="utf-8")
    patch = _modify_patch("hello.txt", "Hello World", "Hello without gate")
    _write_agent_patch(tmp_path, task.id, "agent-a", patch)

    with pytest.raises(PatchApplicationError, match="fresh acceptable patch-review and patch-dry-run evidence"):
        apply_task_patch_command(tmp_path, task.id, agent_id="agent-a")

    assert hello_file.read_text(encoding="utf-8") == "Hello World\n"
    assert not (_task_path(tmp_path, task.id) / "patch-application.json").exists()


def test_apply_task_patch_command_refuses_duplicate_patch_hash(tmp_path: Path) -> None:
    task = create_task(tmp_path, "module duplicate apply")
    hello_file = _workspace_path(tmp_path, task.id) / "hello.txt"
    hello_file.write_text("Hello World\n", encoding="utf-8")
    patch = _modify_patch("hello.txt", "Hello World", "Hello once")
    _write_agent_patch(tmp_path, task.id, "agent-a", patch)
    _write_reviewed_dry_run(tmp_path, task.id, patch, run_id="agent-agent-a")
    apply_task_patch_command(tmp_path, task.id, agent_id="agent-a")

    with pytest.raises(PatchApplicationError, match="Patch was already applied to this workspace"):
        apply_task_patch_command(tmp_path, task.id, agent_id="agent-a")


def test_service_apply_task_patch_facade_delegates_to_module(tmp_path: Path) -> None:
    task = create_task(tmp_path, "service facade apply")
    hello_file = _workspace_path(tmp_path, task.id) / "hello.txt"
    hello_file.write_text("Hello World\n", encoding="utf-8")
    patch = _modify_patch("hello.txt", "Hello World", "Hello facade")
    _write_reviewed_dry_run(tmp_path, task.id, patch, run_id="run-facade")

    updated = service_apply_task_patch(tmp_path, task.id, run_id="run-facade")

    assert updated.status == "complete"
    assert hello_file.read_text(encoding="utf-8") == "Hello facade\n"
    assert _patch_application(tmp_path, task.id)["run_id"] == "run-facade"
