import os
import json
import tempfile
from pathlib import Path
from typer.testing import CliRunner
from devflow.cli import app

runner = CliRunner()


def _write_reviewed_dry_run(tmp: Path, task_id: str, patch: str, *, run_id: str = "run-1") -> None:
    run_path = tmp / ".devflow" / "tasks" / task_id / "local-model-runs" / run_id
    run_path.mkdir(parents=True, exist_ok=True)
    patch_rel = f".devflow/tasks/{task_id}/local-model-runs/{run_id}/proposal.patch"
    review_rel = f".devflow/tasks/{task_id}/local-model-runs/{run_id}/patch-review.json"
    (run_path / "proposal.patch").write_text(patch, encoding="utf-8")
    (run_path / "patch-review.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "task_id": task_id,
                "run_id": run_id,
                "patch_path": patch_rel,
                "review_status": "low_risk_candidate",
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
                "dry_run_status": "would_apply_cleanly",
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
            _write_reviewed_dry_run(tmp, task_id, diff)
            
            # Invoke CLI
            res_apply = runner.invoke(app, ["task", "apply-patch", task_id])
            assert res_apply.exit_code == 0
            assert "Successfully applied patch from agent 'agent-45'" in res_apply.output
            assert "Patch Evidence: .devflow/tasks/task-0001/patches/" in res_apply.output
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


def test_cli_apply_patch_from_reviewed_run_id():
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp = Path(tmp_dir)
        try:
            os.chdir(tmp)
            import shutil

            shutil.copytree(old_cwd / "src", tmp / "src", symlinks=True)
            assert runner.invoke(app, ["init"]).exit_code == 0
            assert runner.invoke(app, ["task", "create", "test CLI run patch task"]).exit_code == 0
            task_id = "task-0001"
            test_file = tmp / ".devflow" / "workspaces" / task_id / "hello.txt"
            test_file.write_text("Hello\n", encoding="utf-8")
            diff = (
                "--- a/hello.txt\n"
                "+++ b/hello.txt\n"
                "@@ -1 +1 @@\n"
                "-Hello\n"
                "+Hello From Run\n"
            )
            _write_reviewed_dry_run(tmp, task_id, diff, run_id="run-apply")

            res_apply = runner.invoke(app, ["task", "apply-patch", task_id, "--run-id", "run-apply"])

            assert res_apply.exit_code == 0, res_apply.output
            assert "Run ID: run-apply" in res_apply.output
            assert "Hello From Run\n" == test_file.read_text(encoding="utf-8")
        finally:
            os.chdir(old_cwd)
