"""Tests for `devflow task list` verification visibility.

Task list uses the shared control-room status projection.
These tests confirm:
- list displays verification status when available
- list handles missing / no-verification-yet gracefully
- list is read-only and does not mutate task files
- list does not depend on packet.json or summary.json
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from typer.testing import CliRunner

from devflow.cli import app
from devflow.legacy.control_room.status_projection import format_verify_token
from devflow.legacy.control_room.service import get_task

runner = CliRunner()


# ---------------------------------------------------------------------------
# verify token unit tests (pure function, no I/O)
# ---------------------------------------------------------------------------


def test_verify_token_not_run() -> None:
    assert format_verify_token("not_run", None) == "not_run"


def test_verify_token_passed() -> None:
    assert format_verify_token("passed", 0) == "passed"
    assert format_verify_token("passed", None) == "passed"


def test_verify_token_failed_with_exit_code() -> None:
    token = format_verify_token("failed", 2)
    assert token == "failed(exit=2)"


def test_verify_token_failed_without_exit_code() -> None:
    assert format_verify_token("failed", None) == "failed"


def test_verify_token_none_status_defaults_to_not_run() -> None:
    assert format_verify_token(None, None) == "not_run"


# ---------------------------------------------------------------------------
# list shows verification status from task.yaml (canonical source)
# ---------------------------------------------------------------------------


def test_list_shows_verification_status_passed() -> None:
    """task list shows 'passed' in verify column when verification passed."""
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)

            runner.invoke(app, ["task", "create", "verify pass task"])
            runner.invoke(app, ["task", "run", "task-0001", "--shell", "echo done"])
            runner.invoke(app, ["task", "verify", "task-0001", "--shell", "exit 0"])

            task = get_task(Path.cwd(), "task-0001")
            assert task.verification_status == "passed"

            listing = runner.invoke(app, ["task", "list"])
            assert listing.exit_code == 0, listing.output
            assert "task-0001" in listing.output
            assert "passed" in listing.output
            assert "verified" in listing.output  # task status column
        finally:
            os.chdir(old_cwd)


def test_list_shows_verification_status_failed_with_exit_code() -> None:
    """task list shows 'failed(exit=N)' in verify column when verification failed."""
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)

            runner.invoke(app, ["task", "create", "verify fail task"])
            runner.invoke(app, ["task", "run", "task-0001", "--shell", "echo done"])
            runner.invoke(app, ["task", "verify", "task-0001", "--shell", "exit 3"])

            task = get_task(Path.cwd(), "task-0001")
            assert task.verification_status == "failed"
            assert task.verification_exit_code == 3

            listing = runner.invoke(app, ["task", "list"])
            assert listing.exit_code == 0, listing.output
            assert "task-0001" in listing.output
            assert "failed(exit=3)" in listing.output
        finally:
            os.chdir(old_cwd)


def test_list_shows_not_run_for_fresh_task() -> None:
    """task list shows 'not_run' in verify column for a task that has not been verified."""
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)

            runner.invoke(app, ["task", "create", "fresh task"])

            task = get_task(Path.cwd(), "task-0001")
            assert task.verification_status == "not_run"

            listing = runner.invoke(app, ["task", "list"])
            assert listing.exit_code == 0, listing.output
            assert "task-0001" in listing.output
            assert "not_run" in listing.output
        finally:
            os.chdir(old_cwd)


def test_list_multiple_tasks_each_shows_own_verify_status() -> None:
    """task list shows per-task verification status for multiple tasks."""
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)

            runner.invoke(app, ["task", "create", "task one"])
            runner.invoke(app, ["task", "create", "task two"])
            runner.invoke(app, ["task", "create", "task three"])

            # Run and verify task-0001 (pass)
            runner.invoke(app, ["task", "run", "task-0001", "--shell", "echo ok"])
            runner.invoke(app, ["task", "verify", "task-0001", "--shell", "exit 0"])

            # Run and verify task-0002 (fail)
            runner.invoke(app, ["task", "run", "task-0002", "--shell", "echo ok"])
            runner.invoke(app, ["task", "verify", "task-0002", "--shell", "exit 7"])

            # task-0003 remains unrun

            listing = runner.invoke(app, ["task", "list"])
            assert listing.exit_code == 0, listing.output
            assert "passed" in listing.output
            assert "failed(exit=7)" in listing.output
            assert "not_run" in listing.output
        finally:
            os.chdir(old_cwd)


# ---------------------------------------------------------------------------
# list handles missing verification gracefully
# ---------------------------------------------------------------------------


def test_list_graceful_when_verification_status_is_not_run() -> None:
    """task list handles not_run verification status without error."""
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)
            runner.invoke(app, ["task", "create", "fresh"])
            listing = runner.invoke(app, ["task", "list"])
            assert listing.exit_code == 0, listing.output
            assert "task-0001" in listing.output
        finally:
            os.chdir(old_cwd)


def test_list_graceful_when_no_tasks_exist() -> None:
    """task list reports 'No tasks found.' when .devflow/tasks is empty."""
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)
            listing = runner.invoke(app, ["task", "list"])
            assert listing.exit_code == 0, listing.output
            assert "No tasks found." in listing.output
        finally:
            os.chdir(old_cwd)


def test_active_list_excludes_promoted_tasks() -> None:
    """--active should hide tasks that no longer need project-queue attention."""
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)
            runner.invoke(app, ["task", "create", "active task"])
            runner.invoke(app, ["task", "create", "already promoted"])

            task_yaml = Path(".devflow/tasks/task-0002/task.yaml")
            task_yaml.write_text(
                task_yaml.read_text(encoding="utf-8").replace('status: "created"', 'status: "promoted"'),
                encoding="utf-8",
            )

            listing = runner.invoke(app, ["task", "list", "--active"])
            assert listing.exit_code == 0, listing.output
            assert "task-0001" in listing.output
            assert "task-0002" not in listing.output
        finally:
            os.chdir(old_cwd)


# ---------------------------------------------------------------------------
# list is read-only — does not mutate any task files
# ---------------------------------------------------------------------------


def test_list_does_not_mutate_task_files() -> None:
    """task list must be a pure read — no file should be written or modified."""
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)
            runner.invoke(app, ["task", "create", "immutable task"])

            task_path = Path(".devflow/tasks/task-0001")
            before: dict[str, bytes] = {}
            for p in sorted(task_path.glob("**/*")):
                if p.is_file():
                    before[str(p)] = p.read_bytes()

            # Invoke list twice to ensure no side effects
            listing1 = runner.invoke(app, ["task", "list"])
            listing2 = runner.invoke(app, ["task", "list"])
            assert listing1.exit_code == 0
            assert listing2.exit_code == 0

            after: dict[str, bytes] = {}
            for p in sorted(task_path.glob("**/*")):
                if p.is_file():
                    after[str(p)] = p.read_bytes()

            assert before == after, "task list must not mutate any task files"
        finally:
            os.chdir(old_cwd)


# ---------------------------------------------------------------------------
# list does NOT depend on packet.json or summary.json
# ---------------------------------------------------------------------------


def test_list_works_without_packet_json() -> None:
    """task list must not require packet.json to display correct output."""
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)
            runner.invoke(app, ["task", "create", "no packet"])
            runner.invoke(app, ["task", "run", "task-0001", "--shell", "echo ok"])
            runner.invoke(app, ["task", "verify", "task-0001", "--shell", "exit 0"])

            # Remove packet.json if it exists
            packet_path = Path(".devflow/tasks/task-0001/packet.json")
            if packet_path.exists():
                packet_path.unlink()
            assert not packet_path.exists()

            listing = runner.invoke(app, ["task", "list"])
            assert listing.exit_code == 0, listing.output
            assert "task-0001" in listing.output
            assert "passed" in listing.output
        finally:
            os.chdir(old_cwd)


def test_list_works_without_summary_json() -> None:
    """task list must not require summary.json to display correct output."""
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)
            runner.invoke(app, ["task", "create", "no summary"])
            runner.invoke(app, ["task", "run", "task-0001", "--shell", "echo ok"])
            runner.invoke(app, ["task", "verify", "task-0001", "--shell", "exit 0"])

            # Remove summary.json to confirm list does not depend on it
            summary_path = Path(".devflow/tasks/task-0001/summary.json")
            if summary_path.exists():
                summary_path.unlink()
            assert not summary_path.exists()

            listing = runner.invoke(app, ["task", "list"])
            assert listing.exit_code == 0, listing.output
            assert "task-0001" in listing.output
            assert "passed" in listing.output
        finally:
            os.chdir(old_cwd)


def test_list_with_stale_packet_json_shows_canonical_task_yaml_status() -> None:
    """Stale packet.json must not pollute the list output — task.yaml is canonical."""
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)
            runner.invoke(app, ["task", "create", "stale packet test"])
            runner.invoke(app, ["task", "run", "task-0001", "--shell", "echo ok"])
            runner.invoke(app, ["task", "verify", "task-0001", "--shell", "exit 0"])

            # Overwrite packet.json with stale/incorrect data claiming verification failed
            packet_path = Path(".devflow/tasks/task-0001/packet.json")
            stale_packet = {
                "task_id": "task-0001",
                "verification_status": "failed",  # stale claim
                "status": "verification_failed",   # stale claim
            }
            packet_path.write_text(json.dumps(stale_packet, indent=2), encoding="utf-8")

            # task.yaml must still be authoritative
            task = get_task(Path.cwd(), "task-0001")
            assert task.verification_status == "passed"

            listing = runner.invoke(app, ["task", "list"])
            assert listing.exit_code == 0, listing.output
            # Shows 'passed' from task.yaml, not 'failed' from stale packet.json
            assert "passed" in listing.output
        finally:
            os.chdir(old_cwd)


def test_list_with_stale_summary_json_shows_canonical_task_yaml_status() -> None:
    """Stale summary.json must not pollute the list output — task.yaml is canonical."""
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)
            runner.invoke(app, ["task", "create", "stale summary test"])
            runner.invoke(app, ["task", "run", "task-0001", "--shell", "echo ok"])
            runner.invoke(app, ["task", "verify", "task-0001", "--shell", "exit 0"])

            # Overwrite summary.json with stale data
            summary_path = Path(".devflow/tasks/task-0001/summary.json")
            stale_summary = {
                "task_id": "task-0001",
                "latest_verification_status": "failed",  # stale claim
                "status": "verification_failed",          # stale claim
                "merge_ready": False,
            }
            summary_path.write_text(json.dumps(stale_summary, indent=2), encoding="utf-8")

            # task.yaml must still be authoritative
            task = get_task(Path.cwd(), "task-0001")
            assert task.verification_status == "passed"

            listing = runner.invoke(app, ["task", "list"])
            assert listing.exit_code == 0, listing.output
            # Shows 'passed' from task.yaml, not 'failed' from stale summary.json
            assert "passed" in listing.output
        finally:
            os.chdir(old_cwd)


# ---------------------------------------------------------------------------
# header / format contract
# ---------------------------------------------------------------------------


def test_list_header_columns_present() -> None:
    """task list always emits a header with Task, Status, Verify, Updated, Title columns."""
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)
            runner.invoke(app, ["task", "create", "header check"])

            listing = runner.invoke(app, ["task", "list"])
            assert listing.exit_code == 0, listing.output
            assert "Task" in listing.output
            assert "Status" in listing.output
            assert "Verify" in listing.output
            assert "Updated" in listing.output
            assert "Title" in listing.output
        finally:
            os.chdir(old_cwd)
