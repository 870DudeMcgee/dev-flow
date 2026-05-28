from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest
from typer.testing import CliRunner

from devflow.cli import app
from devflow.control_room.token_context import detect_context_mode, recommended_tools_for_mode


runner = CliRunner()


def test_context_mode_detection_and_tool_mapping() -> None:
    assert detect_context_mode("review the regression risk") == "review-graph"
    assert recommended_tools_for_mode("review-graph") == ["code-review-graph", "token-optimizer"]

    assert detect_context_mode("debug failing tests from traceback") == "debug-focused"
    assert recommended_tools_for_mode("debug-focused") == ["token-optimizer"]

    assert detect_context_mode("plan the architecture roadmap") == "planning"
    assert recommended_tools_for_mode("planning") == ["intent-layer", "token-optimizer"]

    assert detect_context_mode("explain the README docs") == "docs"
    assert recommended_tools_for_mode("docs") == ["token-optimizer"]

    assert detect_context_mode("add a small command") == "balanced"
    assert recommended_tools_for_mode("balanced") == ["token-optimizer"]


def test_context_command_writes_visible_packet_without_token_tools() -> None:
    _skip_without_git()
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        try:
            os.chdir(repo)
            _git(repo, "init", "-b", "main")
            Path("README.md").write_text("hello\n", encoding="utf-8")

            assert runner.invoke(app, ["init"]).exit_code == 0
            created = runner.invoke(app, ["task", "create", "Existing context task"])
            assert created.exit_code == 0, created.output

            result = runner.invoke(app, ["context", "review regression risk in the CLI"])
            assert result.exit_code == 0, result.output
            assert "mode: review-graph" in result.output
            assert "recommended_tools: code-review-graph, token-optimizer" in result.output

            packet = Path(".devflow/token-context/current.md")
            assert packet.exists()
            body = packet.read_text(encoding="utf-8")

            assert "# Dev-Flow Token Context Packet" in body
            assert "review regression risk in the CLI" in body
            assert "Context Mode: review-graph" in body
            assert "code-review-graph" in body
            assert "token-optimizer" in body
            assert f"Repo Root: {repo.resolve()}" in body
            assert "Current Branch: main" in body
            assert "?? .devflow/" in body
            assert "?? README.md" in body
            assert "task-0001" in body
            assert "Existing context task" in body
            assert "Read this token-context packet first." in body
            assert "Read the current git diff next." in body
            assert "Read changed files before expanding to neighboring files." in body
            assert "Do not read unrelated legacy files as authority." in body
            assert "Do not expand context just because it is available." in body
            assert "For review tasks, review changed files and dependency-adjacent files first." in body
            assert "No token tools were executed by this command." in body
        finally:
            os.chdir(old_cwd)


def test_context_command_appends_event_record() -> None:
    _skip_without_git()
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        try:
            os.chdir(repo)
            _git(repo, "init", "-b", "main")

            first = runner.invoke(app, ["context", "plan the architecture"])
            assert first.exit_code == 0, first.output
            second = runner.invoke(app, ["context", "debug failing test"])
            assert second.exit_code == 0, second.output

            events_path = Path(".devflow/token-context/events.jsonl")
            events = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines()]

            assert [event["event"] for event in events] == ["token_context_planned", "token_context_planned"]
            assert events[0]["context_mode"] == "planning"
            assert events[0]["recommended_tools"] == ["intent-layer", "token-optimizer"]
            assert events[0]["task_description"] == "plan the architecture"
            assert events[0]["packet_path"] == ".devflow/token-context/current.md"
            assert events[1]["context_mode"] == "debug-focused"
            assert events[1]["recommended_tools"] == ["token-optimizer"]
        finally:
            os.chdir(old_cwd)


def test_context_command_in_subdirectory_of_git_repo() -> None:
    _skip_without_git()
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        try:
            os.chdir(repo)
            _git(repo, "init", "-b", "main")
            Path("README.md").write_text("hello\n", encoding="utf-8")
            _git(repo, "add", "README.md")
            _git(repo, "commit", "-m", "initial")

            # Create subdirectory and initialize devflow inside it
            subdir = repo / "subdir"
            subdir.mkdir()
            os.chdir(subdir)

            assert runner.invoke(app, ["init"]).exit_code == 0
            created = runner.invoke(app, ["task", "create", "Subdirectory task"])
            assert created.exit_code == 0, created.output

            result = runner.invoke(app, ["context", "review subdir changes"])
            assert result.exit_code == 0, result.output
            assert "mode: review-graph" in result.output

            packet = subdir / ".devflow" / "token-context" / "current.md"
            assert packet.exists()
            body = packet.read_text(encoding="utf-8")

            # Git repo root should still point to parent repo
            assert f"Repo Root: {repo.resolve()}" in body
            # Task should be read from the subdirectory devflow (where the task was created)
            assert "task-0001" in body
            assert "Subdirectory task" in body
        finally:
            os.chdir(old_cwd)


def test_context_handles_corrupted_tasks_gracefully() -> None:
    _skip_without_git()
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        try:
            os.chdir(repo)
            _git(repo, "init", "-b", "main")

            assert runner.invoke(app, ["init"]).exit_code == 0
            created = runner.invoke(app, ["task", "create", "Valid Task"])
            assert created.exit_code == 0, created.output

            # Corrupt the task.yaml by writing invalid lines
            task_yaml = repo / ".devflow" / "tasks" / "task-0001" / "task.yaml"
            task_yaml.write_text("this is completely invalid yaml no colon\n", encoding="utf-8")

            result = runner.invoke(app, ["context", "review things"])
            assert result.exit_code == 0, result.output
            packet = repo / ".devflow" / "token-context" / "current.md"
            assert packet.exists()
            body = packet.read_text(encoding="utf-8")

            # Should fall back to "task state unreadable" rather than crashing the command
            assert "task state unreadable" in body
        finally:
            os.chdir(old_cwd)


def test_context_show_prints_existing_packet() -> None:
    _skip_without_git()
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        try:
            os.chdir(repo)
            _git(repo, "init", "-b", "main")
            assert runner.invoke(app, ["init"]).exit_code == 0

            # Plan a context packet first
            plan_res = runner.invoke(app, ["context", "plan a new feature"])
            assert plan_res.exit_code == 0, plan_res.output

            # Now show the packet
            show_res = runner.invoke(app, ["context", "--show"])
            assert show_res.exit_code == 0, show_res.output
            assert "# Dev-Flow Token Context Packet" in show_res.output
            assert "plan a new feature" in show_res.output
        finally:
            os.chdir(old_cwd)


def test_context_show_gracefully_handles_missing_packet() -> None:
    _skip_without_git()
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        try:
            os.chdir(repo)
            # Not initializing devflow, so no context packet exists
            show_res = runner.invoke(app, ["context", "--show"])
            assert show_res.exit_code == 0, show_res.output
            assert "No token-context packet found." in show_res.output
            assert 'devflow context "<task description>"' in show_res.output
        finally:
            os.chdir(old_cwd)


def _skip_without_git() -> None:
    if shutil.which("git") is None:
        pytest.skip("git is required for context packet repo-state tests")


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, text=True, capture_output=True)


def test_token_context_summary_logic_and_limits() -> None:
    _skip_without_git()
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        try:
            os.chdir(repo)
            _git(repo, "init", "-b", "main")
            assert runner.invoke(app, ["init"]).exit_code == 0

            # Create three tasks
            assert runner.invoke(app, ["task", "create", "Task One"]).exit_code == 0
            assert runner.invoke(app, ["task", "create", "Task Two"]).exit_code == 0
            assert runner.invoke(app, ["task", "create", "Task Three"]).exit_code == 0

            # 1. Verification that token_context reads valid summary.json when present
            summary_one = repo / ".devflow" / "tasks" / "task-0001" / "summary.json"
            assert summary_one.exists()

            result = runner.invoke(app, ["context", "test summary ingestion"])
            assert result.exit_code == 0, result.output
            body = Path(".devflow/token-context/current.md").read_text(encoding="utf-8")
            assert "task-0001 created: Task One" in body
            assert "task-0002 created: Task Two" in body
            assert "task-0003 created: Task Three" in body

            # 2. Missing summary.json falls back to task.yaml/canonical state
            summary_one.unlink()
            result_missing = runner.invoke(app, ["context", "test summary fallback"])
            assert result_missing.exit_code == 0, result_missing.output
            body_missing = Path(".devflow/token-context/current.md").read_text(encoding="utf-8")
            assert "task-0001 created: Task One" in body_missing

            # 3. Malformed summary.json falls back safely to task.yaml
            summary_one.write_text("{corrupted json", encoding="utf-8")
            result_malformed = runner.invoke(app, ["context", "test summary malformed"])
            assert result_malformed.exit_code == 0, result_malformed.output
            body_malformed = Path(".devflow/token-context/current.md").read_text(encoding="utf-8")
            assert "task-0001 created: Task One" in body_malformed

            # 4. Tampered summary.json (ID mismatch) does not override canonical status/identity
            summary_one.write_text(json.dumps({
                "task_id": "task-tampered-id",
                "title": "Tampered Title",
                "status": "verified",
                "updated_at": "2026-05-28T09:00:00+00:00"
            }), encoding="utf-8")

            result_tampered = runner.invoke(app, ["context", "test summary tampered"])
            assert result_tampered.exit_code == 0, result_tampered.output
            body_tampered = Path(".devflow/token-context/current.md").read_text(encoding="utf-8")
            # Should NOT show the tampered title/status, but the canonical ones from task.yaml
            assert "task-0001 created: Task One" in body_tampered
            assert "Tampered Title" not in body_tampered

            # Restore valid summary.json
            assert runner.invoke(app, ["task", "run", "task-0001", "--shell", "echo restored"]).exit_code == 0

            # 5. Task summaries are limited deterministically to the most recently updated tasks
            # Let's create more tasks so we have 7 tasks total
            assert runner.invoke(app, ["task", "create", "Task Four"]).exit_code == 0
            assert runner.invoke(app, ["task", "create", "Task Five"]).exit_code == 0
            assert runner.invoke(app, ["task", "create", "Task Six"]).exit_code == 0
            assert runner.invoke(app, ["task", "create", "Task Seven"]).exit_code == 0

            # Run context and check that it shows a truncation note / only shows the top 5
            result_limit = runner.invoke(app, ["context", "test limit"])
            assert result_limit.exit_code == 0, result_limit.output
            body_limit = Path(".devflow/token-context/current.md").read_text(encoding="utf-8")

            # It should show "Task Seven", "Task Six", "Task Five", "Task Four", "Task One"
            # and omit Task Three and Task Two
            assert "Task Seven" in body_limit
            assert "Task Six" in body_limit
            assert "Task Five" in body_limit
            assert "Task Four" in body_limit
            assert "Task One" in body_limit
            assert "Task Three" not in body_limit
            assert "Task Two" not in body_limit

            # 6. Omitted task count note is visible
            assert "and 2 more task(s) omitted" in body_limit
        finally:
            os.chdir(old_cwd)