import pytest
import shutil
import json
from pathlib import Path
from devflow.control_room.service import create_task, apply_task_patch
from devflow.control_room.patch_applier import PatchSelectionError, PatchApplicationError

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
    assert len(applied_events[0]["changed_files"]) == 1
    assert applied_events[0]["changed_files"][0]["path"] == "hello.txt"

    
    # Idempotency block
    with pytest.raises(PatchApplicationError, match="already applied"):
        apply_task_patch(tmp_path, task.id)
