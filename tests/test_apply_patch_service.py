import pytest
import shutil
import json
from pathlib import Path
from devflow.legacy.control_room.service import create_task, apply_task_patch, verify_task
from devflow.legacy.control_room.patch_applier import PatchApplicationError


def _write_reviewed_dry_run(
    task_path: Path,
    task_id: str,
    patch: str,
    *,
    run_id: str = "run-1",
    review_status: str = "low_risk_candidate",
    dry_run_status: str = "would_apply_cleanly",
) -> Path:
    run_path = task_path / "local-model-runs" / run_id
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

def test_service_apply_patch_flow(tmp_path: Path):
    shutil.copytree(Path.cwd() / "src", tmp_path / "src", symlinks=True)
    
    # Create a task
    task = create_task(tmp_path, "apply patch service task")
    task_path = tmp_path / ".devflow" / "tasks" / task.id
    workspace_path = tmp_path / ".devflow" / "workspaces" / task.id
    
    # Create target workspace file
    hello_file = workspace_path / "hello.txt"
    hello_file.write_text("Hello World\n", encoding="utf-8")
    
    # Set up mock patch
    agent_dir = task_path / "agents" / "test_agent"
    agent_dir.mkdir(parents=True)
    patch_file = agent_dir / "proposal.patch"
    diff = (
        "--- a/hello.txt\n"
        "+++ b/hello.txt\n"
        "@@ -1 +1 @@\n"
        "-Hello World\n"
        "+Hello service World\n"
    )
    patch_file.write_text(diff, encoding="utf-8")
    _write_reviewed_dry_run(task_path, task.id, diff)
    
    # Apply patch
    updated_task = apply_task_patch(tmp_path, task.id)
    assert hello_file.read_text(encoding="utf-8") == "Hello service World\n"
    
    # Verify event log exists
    events_file = task_path / "events.jsonl"
    assert events_file.exists()
    lines = events_file.read_text(encoding="utf-8").splitlines()
    applied_events = [json.loads(line) for line in lines if "patch_applied" in line]
    assert len(applied_events) == 1
    assert applied_events[0]["agent_id"] == "test_agent"
    assert applied_events[0]["patch_hash"]
    assert len(applied_events[0]["changed_files"]) == 1
    assert applied_events[0]["changed_files"][0]["path"] == "hello.txt"

    evidence_path = task_path / "patches" / f"{applied_events[0]['patch_hash']}.json"
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert evidence["schema_version"] == 1
    assert evidence["task_id"] == task.id
    assert evidence["agent_id"] == "test_agent"
    assert evidence["patch_path"] == f".devflow/tasks/{task.id}/agents/test_agent/proposal.patch"
    assert evidence["patch_hash"] == applied_events[0]["patch_hash"]
    assert evidence["changed_files"][0]["operation"] == "modified"

    latest_evidence = json.loads((task_path / "patch-application.json").read_text(encoding="utf-8"))
    assert latest_evidence["patch_hash"] == applied_events[0]["patch_hash"]

    
    # Idempotency block
    with pytest.raises(PatchApplicationError, match="already applied"):
        apply_task_patch(tmp_path, task.id)


def test_apply_patch_requires_review_and_dry_run_before_mutation(tmp_path: Path):
    shutil.copytree(Path.cwd() / "src", tmp_path / "src", symlinks=True)
    task = create_task(tmp_path, "apply patch gate task")
    task_path = tmp_path / ".devflow" / "tasks" / task.id
    workspace_path = tmp_path / ".devflow" / "workspaces" / task.id
    hello_file = workspace_path / "hello.txt"
    hello_file.write_text("Hello World\n", encoding="utf-8")
    agent_dir = task_path / "agents" / "test_agent"
    agent_dir.mkdir(parents=True)
    diff = (
        "--- a/hello.txt\n"
        "+++ b/hello.txt\n"
        "@@ -1 +1 @@\n"
        "-Hello World\n"
        "+Hello gated World\n"
    )
    (agent_dir / "proposal.patch").write_text(diff, encoding="utf-8")

    with pytest.raises(PatchApplicationError, match="fresh acceptable patch-review and patch-dry-run evidence"):
        apply_task_patch(tmp_path, task.id, agent_id="test_agent")

    assert hello_file.read_text(encoding="utf-8") == "Hello World\n"


def test_apply_patch_rejects_stale_dry_run_evidence(tmp_path: Path):
    shutil.copytree(Path.cwd() / "src", tmp_path / "src", symlinks=True)
    task = create_task(tmp_path, "apply patch stale gate task")
    task_path = tmp_path / ".devflow" / "tasks" / task.id
    workspace_path = tmp_path / ".devflow" / "workspaces" / task.id
    hello_file = workspace_path / "hello.txt"
    hello_file.write_text("Hello World\n", encoding="utf-8")
    agent_dir = task_path / "agents" / "test_agent"
    agent_dir.mkdir(parents=True)
    reviewed_diff = (
        "--- a/hello.txt\n"
        "+++ b/hello.txt\n"
        "@@ -1 +1 @@\n"
        "-Hello World\n"
        "+Hello reviewed World\n"
    )
    changed_diff = reviewed_diff.replace("reviewed", "changed")
    (agent_dir / "proposal.patch").write_text(changed_diff, encoding="utf-8")
    _write_reviewed_dry_run(task_path, task.id, reviewed_diff)

    with pytest.raises(PatchApplicationError, match="matching reviewed dry-run evidence"):
        apply_task_patch(tmp_path, task.id, agent_id="test_agent")

    assert hello_file.read_text(encoding="utf-8") == "Hello World\n"


def test_apply_patch_can_apply_reviewed_local_model_run(tmp_path: Path):
    shutil.copytree(Path.cwd() / "src", tmp_path / "src", symlinks=True)
    task = create_task(tmp_path, "apply local run patch task")
    task_path = tmp_path / ".devflow" / "tasks" / task.id
    workspace_path = tmp_path / ".devflow" / "workspaces" / task.id
    hello_file = workspace_path / "hello.txt"
    hello_file.write_text("Hello World\n", encoding="utf-8")
    diff = (
        "--- a/hello.txt\n"
        "+++ b/hello.txt\n"
        "@@ -1 +1 @@\n"
        "-Hello World\n"
        "+Hello local run World\n"
    )
    _write_reviewed_dry_run(task_path, task.id, diff, run_id="run-apply")

    updated_task = apply_task_patch(tmp_path, task.id, run_id="run-apply")

    assert updated_task.id == task.id
    assert hello_file.read_text(encoding="utf-8") == "Hello local run World\n"
    evidence = json.loads((task_path / "patch-application.json").read_text(encoding="utf-8"))
    assert evidence["run_id"] == "run-apply"
    assert evidence["patch_review_path"] == f".devflow/tasks/{task.id}/local-model-runs/run-apply/patch-review.json"
    assert evidence["patch_dry_run_path"] == f".devflow/tasks/{task.id}/local-model-runs/run-apply/patch-dry-run.json"


def test_apply_patch_invalidates_prior_verification_and_readiness(tmp_path: Path):
    shutil.copytree(Path.cwd() / "src", tmp_path / "src", symlinks=True)
    task = create_task(tmp_path, "apply patch invalidates verification task")
    task_path = tmp_path / ".devflow" / "tasks" / task.id
    workspace_path = tmp_path / ".devflow" / "workspaces" / task.id
    hello_file = workspace_path / "hello.txt"
    hello_file.write_text("Hello World\n", encoding="utf-8")
    verified = verify_task(tmp_path, task.id, ["/bin/sh", "-c", "test -f hello.txt"])
    assert verified.verification_status == "passed"

    diff = (
        "--- a/hello.txt\n"
        "+++ b/hello.txt\n"
        "@@ -1 +1 @@\n"
        "-Hello World\n"
        "+Hello needs fresh verification\n"
    )
    _write_reviewed_dry_run(task_path, task.id, diff, run_id="run-after-verify")

    updated_task = apply_task_patch(tmp_path, task.id, run_id="run-after-verify")

    assert updated_task.status == "complete"
    assert updated_task.verification_status == "not_run"
    assert updated_task.verification_exit_code is None
    assert updated_task.verification_log_path is None
    verification = json.loads((task_path / "verification.json").read_text(encoding="utf-8"))
    patch_application = json.loads((task_path / "patch-application.json").read_text(encoding="utf-8"))
    readiness = json.loads((task_path / "merge-readiness.json").read_text(encoding="utf-8"))
    assert verification["status"] == "not_run"
    assert verification["task_status"] == "complete"
    assert verification["invalidated_by_patch_hash"] == patch_application["patch_hash"]
    assert readiness["ready"] is False
    assert "verification status is 'not_run', expected 'passed'" in readiness["reasons"]


def test_verification_after_patch_binds_readiness_to_latest_patch_application(tmp_path: Path):
    shutil.copytree(Path.cwd() / "src", tmp_path / "src", symlinks=True)
    task = create_task(tmp_path, "verify applied patch task")
    task_path = tmp_path / ".devflow" / "tasks" / task.id
    workspace_path = tmp_path / ".devflow" / "workspaces" / task.id
    hello_file = workspace_path / "hello.txt"
    hello_file.write_text("Hello World\n", encoding="utf-8")
    diff = (
        "--- a/hello.txt\n"
        "+++ b/hello.txt\n"
        "@@ -1 +1 @@\n"
        "-Hello World\n"
        "+Hello verified patch\n"
    )
    _write_reviewed_dry_run(task_path, task.id, diff, run_id="run-verified")
    apply_task_patch(tmp_path, task.id, run_id="run-verified")
    patch_application = json.loads((task_path / "patch-application.json").read_text(encoding="utf-8"))

    verified = verify_task(tmp_path, task.id, ["/bin/sh", "-c", "grep -q 'verified patch' hello.txt"])

    verification = json.loads((task_path / "verification.json").read_text(encoding="utf-8"))
    readiness = json.loads((task_path / "merge-readiness.json").read_text(encoding="utf-8"))
    assert verified.verification_status == "passed"
    assert verification["verified_patch_hash"] == patch_application["patch_hash"]
    assert verification["verified_patch_application_path"] == f".devflow/tasks/{task.id}/patch-application.json"
    assert readiness["ready"] is True
