import os
import json
import tempfile
from pathlib import Path
from typer.testing import CliRunner
from devflow.cli import app

runner = CliRunner()

def test_cli_apply_patch_not_found():
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)
            runner.invoke(app, ["init"])
            runner.invoke(app, ["task", "create", "test task"])
            
            res = runner.invoke(app, ["task", "apply-patch", "task-0001"])
            assert res.exit_code == 1
            assert "Error: No patches found" in res.output
        finally:
            os.chdir(old_cwd)


def test_cli_apply_patch_success():
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp = Path(tmp_dir)
        try:
            os.chdir(tmp)
            import shutil
            shutil.copytree(old_cwd / "src", tmp / "src", symlinks=True)
            
            # CLI init
            runner.invoke(app, ["init"])
            # Create a task
            res_create = runner.invoke(app, ["task", "create", "test CLI task"])
            assert res_create.exit_code == 0
            
            task_id = "task-0001"
            
            task_path = tmp / ".devflow" / "tasks" / task_id
            workspace_path = tmp / ".devflow" / "workspaces" / task_id
            
            # Create a file in workspace to patch
            test_file = workspace_path / "hello.txt"
            test_file.write_text("Hello\nLine 2\nLine 3\n", encoding="utf-8")
            
            # Create agent proposal patch
            agent_dir = task_path / "agents" / "agent-45"
            agent_dir.mkdir(parents=True)
            patch_file = agent_dir / "proposal.patch"
            diff = (
                "--- a/hello.txt\n"
                "+++ b/hello.txt\n"
                "@@ -1,3 +1,3 @@\n"
                "-Hello\n"
                "+Hello Beautiful CLI\n"
                " Line 2\n"
                " Line 3\n"
            )
            patch_file.write_text(diff, encoding="utf-8")
            
            # Invoke CLI
            res_apply = runner.invoke(app, ["task", "apply-patch", task_id])
            assert res_apply.exit_code == 0
            assert "Successfully applied patch from agent 'agent-45'" in res_apply.output
            assert "hello.txt (modified)" in res_apply.output
            assert "devflow task verify" in res_apply.output
            
            # Verify file content
            assert test_file.read_text(encoding="utf-8") == "Hello Beautiful CLI\nLine 2\nLine 3\n"
            
            # Verify duplicate application fails via CLI (exit code 1)
            res_apply_again = runner.invoke(app, ["task", "apply-patch", task_id])
            assert res_apply_again.exit_code == 1
            assert "Error:" in res_apply_again.output
            
        finally:
            os.chdir(old_cwd)

