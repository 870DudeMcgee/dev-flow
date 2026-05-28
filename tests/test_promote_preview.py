from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path

import pytest
from typer.testing import CliRunner

from devflow.cli import app
from devflow.control_room.service import get_task

runner = CliRunner()


def test_promote_preview_missing_task() -> None:
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)
            res = runner.invoke(app, ["task", "promote-preview", "task-9999"])
            assert res.exit_code == 1
            assert "Task not found" in res.output or "task-9999" in res.output
        finally:
            os.chdir(old_cwd)


def test_promote_preview_missing_workspace() -> None:
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)
            created = runner.invoke(app, ["task", "create", "test task"])
            assert created.exit_code == 0

            workspace_dir = Path(".devflow/workspaces/task-0001")
            assert workspace_dir.exists()
            shutil.rmtree(workspace_dir)

            res = runner.invoke(app, ["task", "promote-preview", "task-0001"])
            assert res.exit_code == 1
            assert "Workspace directory does not exist" in res.output
        finally:
            os.chdir(old_cwd)


def test_promote_preview_unsafe_workspace() -> None:
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)
            created = runner.invoke(app, ["task", "create", "test task"])
            assert created.exit_code == 0

            yaml_path = Path(".devflow/tasks/task-0001/task.yaml")
            content = yaml_path.read_text(encoding="utf-8")
            content = content.replace('workspace: ".devflow/workspaces/task-0001"', 'workspace: "/usr/bin"')
            yaml_path.write_text(content, encoding="utf-8")

            res = runner.invoke(app, ["task", "promote-preview", "task-0001"])
            assert res.exit_code == 1
            assert "Refusing unsafe task workspace" in res.output
        finally:
            os.chdir(old_cwd)


def test_promote_preview_added_modified_deleted() -> None:
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)
            Path("stay.txt").write_text("unchanged content\n", encoding="utf-8")
            Path("modify.txt").write_text("old content\n", encoding="utf-8")
            Path("delete.txt").write_text("to be deleted\n", encoding="utf-8")

            created = runner.invoke(app, ["task", "create", "preview-test"])
            assert created.exit_code == 0

            workspace_dir = Path(".devflow/workspaces/task-0001")
            assert workspace_dir.exists()

            Path(workspace_dir / "added.txt").write_text("new file\n", encoding="utf-8")
            Path(workspace_dir / "modify.txt").write_text("new content\n", encoding="utf-8")
            Path(workspace_dir / "delete.txt").unlink()

            ignored_dir = workspace_dir / ".venv"
            ignored_dir.mkdir()
            Path(ignored_dir / "venv_file.txt").write_text("ignored\n", encoding="utf-8")

            task_yaml_path = Path(".devflow/tasks/task-0001/task.yaml")
            task_yaml_before = task_yaml_path.read_text(encoding="utf-8")

            res = runner.invoke(app, ["task", "promote-preview", "task-0001"])
            assert res.exit_code == 0, res.output

            assert "Added files:" in res.output
            assert "  - added.txt" in res.output
            assert "Modified files:" in res.output
            assert "  - modify.txt" in res.output
            assert "Deleted files:" in res.output
            assert "  - delete.txt" in res.output

            assert "--- Diffs ---" in res.output
            assert "+++ b/added.txt" in res.output
            assert "+new file" in res.output
            assert "--- a/modify.txt" in res.output
            assert "+++ b/modify.txt" in res.output
            assert "-old content" in res.output
            assert "+new content" in res.output
            assert "--- a/delete.txt" in res.output
            assert "-to be deleted" in res.output

            assert "venv_file.txt" not in res.output
            assert ".venv" not in res.output

            assert task_yaml_path.read_text(encoding="utf-8") == task_yaml_before
        finally:
            os.chdir(old_cwd)


def test_promote_preview_no_changes() -> None:
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)
            Path("file.txt").write_text("content\n", encoding="utf-8")
            created = runner.invoke(app, ["task", "create", "no changes task"])
            assert created.exit_code == 0

            res = runner.invoke(app, ["task", "promote-preview", "task-0001"])
            assert res.exit_code == 0
            assert "No changes to promote" in res.output
        finally:
            os.chdir(old_cwd)


def test_promote_refuses_unverified_task() -> None:
    import subprocess
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)
            subprocess.run(["git", "init", "-b", "main"], check=True)
            subprocess.run(["git", "config", "user.email", "test@example.com"], check=True)
            subprocess.run(["git", "config", "user.name", "Test User"], check=True)
            Path("file.txt").write_text("initial\n", encoding="utf-8")
            subprocess.run(["git", "add", "file.txt"], check=True)
            subprocess.run(["git", "commit", "-m", "init"], check=True)

            created = runner.invoke(app, ["task", "create", "unverified-test"])
            assert created.exit_code == 0

            res = runner.invoke(app, ["task", "promote", "task-0001"])
            assert res.exit_code == 1
            assert "expected 'verified'" in res.output
        finally:
            os.chdir(old_cwd)


def test_promote_declined_confirmation() -> None:
    import subprocess
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)
            subprocess.run(["git", "init", "-b", "main"], check=True)
            subprocess.run(["git", "config", "user.email", "test@example.com"], check=True)
            subprocess.run(["git", "config", "user.name", "Test User"], check=True)
            Path("file.txt").write_text("old\n", encoding="utf-8")
            subprocess.run(["git", "add", "file.txt"], check=True)
            subprocess.run(["git", "commit", "-m", "init"], check=True)

            created = runner.invoke(app, ["task", "create", "decline-test"])
            assert created.exit_code == 0

            workspace_dir = Path(".devflow/workspaces/task-0001")
            Path(workspace_dir / "file.txt").write_text("new\n", encoding="utf-8")

            yaml_path = Path(".devflow/tasks/task-0001/task.yaml")
            content = yaml_path.read_text(encoding="utf-8")
            content = content.replace('status: "created"', 'status: "verified"')
            yaml_path.write_text(content, encoding="utf-8")

            res = runner.invoke(app, ["task", "promote", "task-0001"], input="n\n")
            assert res.exit_code == 0
            assert "Promotion aborted." in res.output

            assert Path("file.txt").read_text(encoding="utf-8") == "old\n"

            task = get_task(Path.cwd(), "task-0001")
            assert task.status == "verified"
        finally:
            os.chdir(old_cwd)


def test_promote_confirmed_copies_added_and_modified_but_not_deleted() -> None:
    import subprocess
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)
            subprocess.run(["git", "init", "-b", "main"], check=True)
            subprocess.run(["git", "config", "user.email", "test@example.com"], check=True)
            subprocess.run(["git", "config", "user.name", "Test User"], check=True)
            Path("stay.txt").write_text("unchanged\n", encoding="utf-8")
            Path("modify.txt").write_text("old modify\n", encoding="utf-8")
            Path("delete.txt").write_text("should stay deleted\n", encoding="utf-8")
            subprocess.run(["git", "add", "stay.txt", "modify.txt", "delete.txt"], check=True)
            subprocess.run(["git", "commit", "-m", "init"], check=True)

            created = runner.invoke(app, ["task", "create", "promote-test"])
            assert created.exit_code == 0

            workspace_dir = Path(".devflow/workspaces/task-0001")
            Path(workspace_dir / "added.txt").write_text("added content\n", encoding="utf-8")
            Path(workspace_dir / "modify.txt").write_text("new modify\n", encoding="utf-8")
            Path(workspace_dir / "delete.txt").unlink()

            yaml_path = Path(".devflow/tasks/task-0001/task.yaml")
            content = yaml_path.read_text(encoding="utf-8")
            content = content.replace('status: "created"', 'status: "verified"')
            yaml_path.write_text(content, encoding="utf-8")

            res = runner.invoke(app, ["task", "promote", "task-0001"], input="y\n")
            assert res.exit_code == 0, res.output
            assert "Promotion complete." in res.output
            assert "Warning: Deletions are preview-only" in res.output

            assert Path("added.txt").read_text(encoding="utf-8") == "added content\n"
            assert Path("modify.txt").read_text(encoding="utf-8") == "new modify\n"
            assert Path("delete.txt").exists()
            assert Path("delete.txt").read_text(encoding="utf-8") == "should stay deleted\n"

            task = get_task(Path.cwd(), "task-0001")
            assert task.status == "promoted"
            assert task.last_event == "task_promoted"

            events_text = Path(".devflow/tasks/task-0001/events.jsonl").read_text(encoding="utf-8")
            assert "task_promoted" in events_text
        finally:
            os.chdir(old_cwd)


def test_promote_dirty_checkout_blocks_by_default() -> None:
    import subprocess
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)
            subprocess.run(["git", "init", "-b", "main"], check=True)
            subprocess.run(["git", "config", "user.email", "test@example.com"], check=True)
            subprocess.run(["git", "config", "user.name", "Test User"], check=True)
            Path("file.txt").write_text("initial\n", encoding="utf-8")
            subprocess.run(["git", "add", "file.txt"], check=True)
            subprocess.run(["git", "commit", "-m", "init"], check=True)

            created = runner.invoke(app, ["task", "create", "dirty-test"])
            assert created.exit_code == 0

            yaml_path = Path(".devflow/tasks/task-0001/task.yaml")
            content = yaml_path.read_text(encoding="utf-8")
            content = content.replace('status: "created"', 'status: "verified"')
            yaml_path.write_text(content, encoding="utf-8")

            Path("dirty.txt").write_text("dirty content\n", encoding="utf-8")

            res = runner.invoke(app, ["task", "promote", "task-0001"])
            assert res.exit_code == 1, res.output
            assert "Error: Main checkout has uncommitted changes." in res.output

            task = get_task(Path.cwd(), "task-0001")
            assert task.status == "verified"
        finally:
            os.chdir(old_cwd)


def test_promote_dirty_checkout_force_bypasses() -> None:
    import subprocess
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)
            subprocess.run(["git", "init", "-b", "main"], check=True)
            subprocess.run(["git", "config", "user.email", "test@example.com"], check=True)
            subprocess.run(["git", "config", "user.name", "Test User"], check=True)
            Path("file.txt").write_text("initial\n", encoding="utf-8")
            subprocess.run(["git", "add", "file.txt"], check=True)
            subprocess.run(["git", "commit", "-m", "init"], check=True)

            created = runner.invoke(app, ["task", "create", "dirty-force-test"])
            assert created.exit_code == 0

            workspace_dir = Path(".devflow/workspaces/task-0001")
            Path(workspace_dir / "added.txt").write_text("added\n", encoding="utf-8")

            yaml_path = Path(".devflow/tasks/task-0001/task.yaml")
            content = yaml_path.read_text(encoding="utf-8")
            content = content.replace('status: "created"', 'status: "verified"')
            yaml_path.write_text(content, encoding="utf-8")

            Path("dirty.txt").write_text("dirty content\n", encoding="utf-8")

            res = runner.invoke(app, ["task", "promote", "task-0001", "--force"], input="y\n")
            assert res.exit_code == 0, res.output
            assert "Warning: Bypassing safety check for uncommitted changes" in res.output
            assert "Promotion complete." in res.output

            assert Path("added.txt").read_text(encoding="utf-8") == "added\n"

            task = get_task(Path.cwd(), "task-0001")
            assert task.status == "promoted"
        finally:
            os.chdir(old_cwd)


def test_promote_devflow_only_dirtiness_does_not_block() -> None:
    import subprocess
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)
            subprocess.run(["git", "init", "-b", "main"], check=True)
            subprocess.run(["git", "config", "user.email", "test@example.com"], check=True)
            subprocess.run(["git", "config", "user.name", "Test User"], check=True)
            Path("file.txt").write_text("initial\n", encoding="utf-8")
            subprocess.run(["git", "add", "file.txt"], check=True)
            subprocess.run(["git", "commit", "-m", "init"], check=True)

            created = runner.invoke(app, ["task", "create", "devflow-dirty-test"])
            assert created.exit_code == 0

            workspace_dir = Path(".devflow/workspaces/task-0001")
            Path(workspace_dir / "added.txt").write_text("added\n", encoding="utf-8")

            yaml_path = Path(".devflow/tasks/task-0001/task.yaml")
            content = yaml_path.read_text(encoding="utf-8")
            content = content.replace('status: "created"', 'status: "verified"')
            yaml_path.write_text(content, encoding="utf-8")

            res = runner.invoke(app, ["task", "promote", "task-0001"], input="y\n")
            assert res.exit_code == 0, res.output
            assert "Error: Main checkout has uncommitted changes" not in res.output
            assert "Promotion complete." in res.output

            assert Path("added.txt").read_text(encoding="utf-8") == "added\n"
        finally:
            os.chdir(old_cwd)


def test_promote_outside_git_repo_fails_safely() -> None:
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)
            created = runner.invoke(app, ["task", "create", "non-git-test"])
            assert created.exit_code == 0

            yaml_path = Path(".devflow/tasks/task-0001/task.yaml")
            content = yaml_path.read_text(encoding="utf-8")
            content = content.replace('status: "created"', 'status: "verified"')
            yaml_path.write_text(content, encoding="utf-8")

            res = runner.invoke(app, ["task", "promote", "task-0001"])
            assert res.exit_code == 1
            assert "Repository root is not a git repository" in res.output
        finally:
            os.chdir(old_cwd)


def test_promote_apply_deletions_confirmed() -> None:
    import subprocess
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)
            subprocess.run(["git", "init", "-b", "main"], check=True)
            subprocess.run(["git", "config", "user.email", "test@example.com"], check=True)
            subprocess.run(["git", "config", "user.name", "Test User"], check=True)
            Path("delete.txt").write_text("delete me\n", encoding="utf-8")
            Path("stay.txt").write_text("stay\n", encoding="utf-8")
            subprocess.run(["git", "add", "delete.txt", "stay.txt"], check=True)
            subprocess.run(["git", "commit", "-m", "init"], check=True)

            created = runner.invoke(app, ["task", "create", "delete-apply-test"])
            assert created.exit_code == 0

            workspace_dir = Path(".devflow/workspaces/task-0001")
            Path(workspace_dir / "delete.txt").unlink()

            yaml_path = Path(".devflow/tasks/task-0001/task.yaml")
            content = yaml_path.read_text(encoding="utf-8")
            content = content.replace('status: "created"', 'status: "verified"')
            yaml_path.write_text(content, encoding="utf-8")

            res = runner.invoke(app, ["task", "promote", "task-0001", "--apply-deletions"], input="y\n")
            assert res.exit_code == 0, res.output
            assert "Applied deletions: 1 file(s) removed." in res.output
            assert "Promotion complete." in res.output

            assert not Path("delete.txt").exists()
            assert Path("stay.txt").exists()

            task = get_task(Path.cwd(), "task-0001")
            assert task.status == "promoted"

            events_text = Path(".devflow/tasks/task-0001/events.jsonl").read_text(encoding="utf-8")
            assert '"deleted_applied": ["delete.txt"]' in events_text
        finally:
            os.chdir(old_cwd)


def test_promote_apply_deletions_declined() -> None:
    import subprocess
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)
            subprocess.run(["git", "init", "-b", "main"], check=True)
            subprocess.run(["git", "config", "user.email", "test@example.com"], check=True)
            subprocess.run(["git", "config", "user.name", "Test User"], check=True)
            Path("delete.txt").write_text("delete me\n", encoding="utf-8")
            subprocess.run(["git", "add", "delete.txt"], check=True)
            subprocess.run(["git", "commit", "-m", "init"], check=True)

            created = runner.invoke(app, ["task", "create", "delete-decline-test"])
            assert created.exit_code == 0

            workspace_dir = Path(".devflow/workspaces/task-0001")
            Path(workspace_dir / "delete.txt").unlink()

            yaml_path = Path(".devflow/tasks/task-0001/task.yaml")
            content = yaml_path.read_text(encoding="utf-8")
            content = content.replace('status: "created"', 'status: "verified"')
            yaml_path.write_text(content, encoding="utf-8")

            res = runner.invoke(app, ["task", "promote", "task-0001", "--apply-deletions"], input="n\n")
            assert res.exit_code == 0
            assert "Promotion aborted." in res.output

            assert Path("delete.txt").exists()

            task = get_task(Path.cwd(), "task-0001")
            assert task.status == "verified"
        finally:
            os.chdir(old_cwd)


def test_promote_apply_deletions_safety_boundaries() -> None:
    import subprocess
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)
            subprocess.run(["git", "init", "-b", "main"], check=True)
            subprocess.run(["git", "config", "user.email", "test@example.com"], check=True)
            subprocess.run(["git", "config", "user.name", "Test User"], check=True)
            Path("stay.txt").write_text("stay\n", encoding="utf-8")
            subprocess.run(["git", "add", "stay.txt"], check=True)
            subprocess.run(["git", "commit", "-m", "init"], check=True)

            created = runner.invoke(app, ["task", "create", "safety-delete-test"])
            assert created.exit_code == 0

            workspace_dir = Path(".devflow/workspaces/task-0001")

            yaml_path = Path(".devflow/tasks/task-0001/task.yaml")
            content = yaml_path.read_text(encoding="utf-8")
            content = content.replace('status: "created"', 'status: "verified"')
            yaml_path.write_text(content, encoding="utf-8")

            from devflow.control_room.service import promote_task
            task = promote_task(Path.cwd(), "task-0001", apply_deletions=True)
            assert task.status == "promoted"
            assert Path("stay.txt").exists()
        finally:
            os.chdir(old_cwd)


def test_promote_harden_copy_escapes_root(monkeypatch: pytest.MonkeyPatch) -> None:
    import subprocess
    from devflow.control_room.service import promote_task
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)
            subprocess.run(["git", "init", "-b", "main"], check=True)
            subprocess.run(["git", "config", "user.email", "test@example.com"], check=True)
            subprocess.run(["git", "config", "user.name", "Test User"], check=True)
            Path("file.txt").write_text("initial\n", encoding="utf-8")
            subprocess.run(["git", "add", "file.txt"], check=True)
            subprocess.run(["git", "commit", "-m", "init"], check=True)

            created = runner.invoke(app, ["task", "create", "escape-test"])
            assert created.exit_code == 0

            # Manually mark verified
            yaml_path = Path(".devflow/tasks/task-0001/task.yaml")
            content = yaml_path.read_text(encoding="utf-8")
            content = content.replace('status: "created"', 'status: "verified"')
            yaml_path.write_text(content, encoding="utf-8")

            # Monkeypatch _get_relative_files to return a path that escapes root
            from devflow.control_room import service
            def mock_get_relative_files(base_dir: Path) -> set[str]:
                if base_dir == Path(tmp):
                    return {"file.txt"}
                return {"../escaped.txt"}
            monkeypatch.setattr(service, "_get_relative_files", mock_get_relative_files)

            # Promoting should raise ValueError
            with pytest.raises(ValueError) as excinfo:
                promote_task(Path(tmp), "task-0001")
            assert "escapes repository root" in str(excinfo.value)

            # Ensure task status was not changed and no task_promoted event is appended
            task = get_task(Path(tmp), "task-0001")
            assert task.status == "verified"

            events_text = (Path(".devflow/tasks/task-0001/events.jsonl")).read_text(encoding="utf-8")
            assert "task_promoted" not in events_text
        finally:
            os.chdir(old_cwd)


def test_promote_harden_copy_ignored_path(monkeypatch: pytest.MonkeyPatch) -> None:
    import subprocess
    from devflow.control_room.service import promote_task
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)
            subprocess.run(["git", "init", "-b", "main"], check=True)
            subprocess.run(["git", "config", "user.email", "test@example.com"], check=True)
            subprocess.run(["git", "config", "user.name", "Test User"], check=True)
            Path("file.txt").write_text("initial\n", encoding="utf-8")
            subprocess.run(["git", "add", "file.txt"], check=True)
            subprocess.run(["git", "commit", "-m", "init"], check=True)

            created = runner.invoke(app, ["task", "create", "ignored-test"])
            assert created.exit_code == 0

            # Manually mark verified
            yaml_path = Path(".devflow/tasks/task-0001/task.yaml")
            content = yaml_path.read_text(encoding="utf-8")
            content = content.replace('status: "created"', 'status: "verified"')
            yaml_path.write_text(content, encoding="utf-8")

            # Monkeypatch _get_relative_files to return a path in .git
            from devflow.control_room import service
            def mock_get_relative_files(base_dir: Path) -> set[str]:
                if base_dir == Path(tmp):
                    return {"file.txt"}
                return {".git/config"}
            monkeypatch.setattr(service, "_get_relative_files", mock_get_relative_files)

            # Promoting should raise ValueError
            with pytest.raises(ValueError) as excinfo:
                promote_task(Path(tmp), "task-0001")
            assert "ignored/control directory" in str(excinfo.value)

            # Ensure task status was not changed and no task_promoted event is appended
            task = get_task(Path(tmp), "task-0001")
            assert task.status == "verified"

            events_text = (Path(".devflow/tasks/task-0001/events.jsonl")).read_text(encoding="utf-8")
            assert "task_promoted" not in events_text
        finally:
            os.chdir(old_cwd)


def test_task_show_promotion_visibility() -> None:
    import subprocess
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)
            subprocess.run(["git", "init", "-b", "main"], check=True)
            subprocess.run(["git", "config", "user.email", "test@example.com"], check=True)
            subprocess.run(["git", "config", "user.name", "Test User"], check=True)
            Path("delete.txt").write_text("delete me\n", encoding="utf-8")
            Path("modify.txt").write_text("old content\n", encoding="utf-8")
            subprocess.run(["git", "add", "delete.txt", "modify.txt"], check=True)
            subprocess.run(["git", "commit", "-m", "init"], check=True)

            created = runner.invoke(app, ["task", "create", "visibility-test"])
            assert created.exit_code == 0

            # 1. Test unpromoted task show does not include promoted_changes
            res_show_created = runner.invoke(app, ["task", "show", "task-0001"])
            assert res_show_created.exit_code == 0
            assert "promoted_changes" not in res_show_created.output

            # Modify files in workspace
            workspace_dir = Path(".devflow/workspaces/task-0001")
            Path(workspace_dir / "added.txt").write_text("new file\n", encoding="utf-8")
            Path(workspace_dir / "modify.txt").write_text("new content\n", encoding="utf-8")
            Path(workspace_dir / "delete.txt").unlink()

            # Mark verified
            yaml_path = Path(".devflow/tasks/task-0001/task.yaml")
            content = yaml_path.read_text(encoding="utf-8")
            content = content.replace('status: "created"', 'status: "verified"')
            yaml_path.write_text(content, encoding="utf-8")

            # 2. Test verified task suggested next action points to devflow task promote
            res_show_verified = runner.invoke(app, ["task", "show", "task-0001"])
            assert res_show_verified.exit_code == 0
            assert "Task is verified. Review promotion preview, then run 'devflow task promote task-0001' when ready." in res_show_verified.output
            assert "promoted_changes" not in res_show_verified.output

            # Promote task with deletions
            res_promote = runner.invoke(app, ["task", "promote", "task-0001", "--apply-deletions"], input="y\n")
            assert res_promote.exit_code == 0

            # 3. Test promoted task show includes promoted added/modified/deleted_applied paths
            res_show_promoted = runner.invoke(app, ["task", "show", "task-0001"])
            assert res_show_promoted.exit_code == 0
            assert "promoted_changes:" in res_show_promoted.output
            assert "  added: added.txt" in res_show_promoted.output
            assert "  modified: modify.txt" in res_show_promoted.output
            assert "  deleted_applied: delete.txt" in res_show_promoted.output

            # 4. Test promoted task suggested next action points to manual review/commit
            assert "suggested_next_action: Task has been promoted. Review main checkout changes, then commit manually if appropriate." in res_show_promoted.output

            # 5. Test malformed event lines do not crash task show
            events_path = Path(".devflow/tasks/task-0001/events.jsonl")
            events_path.write_text(events_path.read_text(encoding="utf-8") + "\nthis is a malformed json line\n", encoding="utf-8")
            res_show_malformed = runner.invoke(app, ["task", "show", "task-0001"])
            assert res_show_malformed.exit_code == 0
            assert "promoted_changes:" in res_show_malformed.output
        finally:
            os.chdir(old_cwd)
