from __future__ import annotations

import json
import subprocess
import threading
from http import HTTPStatus
from http.client import HTTPConnection
from pathlib import Path

import pytest
from typer.testing import CliRunner

import devflow.control_room.operating_layer_actions_agents_task_context_handlers as actions_agents_handlers
import devflow.control_room.operating_layer_server as operating_layer_server
from devflow.cli import app
from devflow.control_room.browser_action_policy import ACTION_APPROVAL_PHRASE
from devflow.control_room.idea_foundry import capture_idea
from devflow.control_room.operating_layer_server import OperatingLayerHTTPServer

runner = CliRunner()


def _serve_operating_layer(root: Path) -> tuple[OperatingLayerHTTPServer, threading.Thread, str, int]:
    server = OperatingLayerHTTPServer(("127.0.0.1", 0), root)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    return server, thread, host, port


def _post_action(host: str, port: int, command: str, *, approved: bool = True, **extra: object) -> tuple[int, dict]:
    connection = HTTPConnection(host, port, timeout=5)
    payload: dict[str, object] = {"command": command}
    if approved:
        payload.update(
            {
                "human_approved": True,
                "approval_phrase": ACTION_APPROVAL_PHRASE,
                "approved_command": command,
            }
        )
    payload.update(extra)
    try:
        connection.request(
            "POST",
            "/api/actions/run",
            body=json.dumps(payload),
            headers={"Content-Type": "application/json"},
        )
        response = connection.getresponse()
        body = json.loads(response.read().decode("utf-8"))
        return response.status, body
    finally:
        connection.close()


def test_operating_layer_server_runs_supervisor_safe_read_only_action(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    assert runner.invoke(app, ["task", "create", "ui control task"]).exit_code == 0

    server, thread, host, port = _serve_operating_layer(tmp_path)
    try:
        status, payload = _post_action(host, port, "devflow task list", approved=False)

        assert status == HTTPStatus.OK
        assert payload["executed"] is True
        assert payload["exit_code"] == 0
        assert payload["classification"]["safety_class"] == "pure_read_only"
        assert "task-0001" in payload["stdout"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_operating_layer_server_blocks_approval_required_actions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    assert runner.invoke(app, ["task", "create", "blocked runtime action"]).exit_code == 0
    worker_log = tmp_path / ".devflow" / "tasks" / "task-0001" / "logs" / "worker.log"
    original_worker_log = worker_log.read_text() if worker_log.exists() else None

    server, thread, host, port = _serve_operating_layer(tmp_path)
    try:
        status, payload = _post_action(host, port, "devflow task run task-0001 --worker qwopus-implementer")

        assert status == HTTPStatus.CONFLICT
        assert payload["executed"] is False
        assert payload["requires_human_approval"] is True
        assert payload["classification"]["safety_class"] == "approval_required_worker_runtime"
        assert (worker_log.read_text() if worker_log.exists() else None) == original_worker_log
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_operating_layer_server_runs_approved_shell_worker_in_task_workspace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    assert runner.invoke(app, ["task", "create", "approved shell worker action"]).exit_code == 0
    command = 'devflow task run task-0001 --worker shell -- /bin/sh -c "printf browser > browser.txt"'
    server, thread, host, port = _serve_operating_layer(tmp_path)
    try:
        status, payload = _post_action(host, port, command)

        assert status == HTTPStatus.OK
        assert payload["executed"] is True
        assert payload["requires_human_approval"] is True
        assert payload["classification"]["safety_class"] == "approval_required_worker_runtime"
        assert payload["exit_code"] == 0
        assert "task-0001: complete" in payload["stdout"]
        workspace_file = tmp_path / ".devflow" / "workspaces" / "task-0001" / "browser.txt"
        assert workspace_file.read_text(encoding="utf-8") == "browser"
        assert not (tmp_path / "browser.txt").exists()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_operating_layer_server_runs_approved_task_verification(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    assert runner.invoke(app, ["task", "create", "approved verification action"]).exit_code == 0
    run = runner.invoke(app, ["task", "run", "task-0001", "--shell", "echo done > result.txt"])
    assert run.exit_code == 0, run.output

    command = 'devflow task verify task-0001 --shell "test -f result.txt"'
    server, thread, host, port = _serve_operating_layer(tmp_path)
    try:
        status, payload = _post_action(host, port, command)

        assert status == HTTPStatus.OK
        assert payload["executed"] is True
        assert payload["requires_human_approval"] is True
        assert payload["classification"]["safety_class"] == "approval_required_worker_runtime"
        assert payload["exit_code"] == 0
        assert "task-0001: verification passed" in payload["stdout"]
        verification = json.loads((tmp_path / ".devflow" / "tasks" / "task-0001" / "verification.json").read_text())
        assert verification["status"] == "passed"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_operating_layer_server_runs_approved_task_promotion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "devflow@example.test"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "DevFlow Test"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "--allow-empty", "-m", "initial"], cwd=tmp_path, check=True, capture_output=True)

    assert runner.invoke(app, ["task", "create", "ship visible approval evidence"]).exit_code == 0
    run = runner.invoke(app, ["task", "run", "task-0001", "--shell", "echo done > approval.txt"])
    assert run.exit_code == 0, run.output
    verify = runner.invoke(app, ["task", "verify", "task-0001", "--shell", "test -f approval.txt"])
    assert verify.exit_code == 0, verify.output
    preview = runner.invoke(app, ["task", "promote-preview", "task-0001"])
    assert preview.exit_code == 0, preview.output

    command = "devflow task promote task-0001"
    context_note = "Ship this because the browser review confirmed the visible approval evidence."
    server, thread, host, port = _serve_operating_layer(tmp_path)
    try:
        status, payload = _post_action(host, port, command, context_note=context_note)

        assert status == HTTPStatus.OK
        assert payload["executed"] is True
        assert payload["requires_human_approval"] is True
        assert payload["classification"]["safety_class"] == "approval_required_git"
        assert payload["exit_code"] == 0
        assert "Promotion complete." in payload["stdout"]
        assert payload["context_path"] == ".devflow/tasks/task-0001/promotion-context.md"
        task_yaml = (tmp_path / ".devflow" / "tasks" / "task-0001" / "task.yaml").read_text()
        assert 'status: "promoted"' in task_yaml
        context = (tmp_path / ".devflow" / "tasks" / "task-0001" / "promotion-context.md").read_text()
        assert context_note in context
        assert "devflow task promote task-0001" in context
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_operating_layer_server_refuses_invalid_shell_worker_browser_runs(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    assert runner.invoke(app, ["task", "create", "refuse invalid shell run"]).exit_code == 0
    server, thread, host, port = _serve_operating_layer(tmp_path)
    try:
        commands = [
            "devflow task run task-0001 --worker shell --",
            "devflow task run task-0001 --worker shell -- <command>",
            "devflow task run task-0001 --worker qwopus-implementer",
            "devflow task local task-0001 --worker qwen-planner",
            "devflow agent run local-gemma4-qat --prompt hello --json",
            "devflow task run task-0001 --worker shell -- ollama run qwen",
        ]
        for command in commands:
            status, payload = _post_action(host, port, command)

            assert status != HTTPStatus.OK
            assert payload.get("executed") is not True
        assert not (tmp_path / ".devflow" / "workspaces" / "task-0001" / "provider.txt").exists()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_operating_layer_server_refuses_empty_or_placeholder_idea_capture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    server, thread, host, port = _serve_operating_layer(tmp_path)
    try:
        for command in ('devflow idea capture', 'devflow idea capture ""', 'devflow idea capture "<idea>"'):
            status, payload = _post_action(host, port, command)

            assert status != HTTPStatus.OK
            assert payload.get("executed") is not True
        assert not (tmp_path / ".devflow" / "ideas" / "I-0001").exists()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_operating_layer_server_refuses_empty_or_placeholder_task_titles(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    server, thread, host, port = _serve_operating_layer(tmp_path)
    try:
        for command in ('devflow task create', 'devflow task create ""', 'devflow task create "<title>"'):
            status, payload = _post_action(host, port, command)

            assert status != HTTPStatus.OK
            assert payload.get("executed") is not True
        assert not (tmp_path / ".devflow" / "tasks" / "task-0001").exists()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_operating_layer_server_blocks_disallowed_browser_mutations(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    assert runner.invoke(app, ["task", "create", "blocked browser mutation"]).exit_code == 0
    server, thread, host, port = _serve_operating_layer(tmp_path)
    try:
        for command in (
            "devflow task apply-patch task-0001",
            "devflow task cleanup task-0001 --apply",
            "devflow sync-main",
            "devflow push-main",
            "devflow project connect-github demo --remote-url https://github.com/example/demo",
        ):
            status, payload = _post_action(host, port, command)

            assert status == HTTPStatus.CONFLICT
            assert payload["executed"] is False
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_operating_layer_approved_model_onboarding_actions_execute(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    assert runner.invoke(app, ["init"]).exit_code == 0
    server, thread, host, port = _serve_operating_layer(tmp_path)
    try:
        add_provider = (
            "devflow agent add-provider local_gateway --adapter openai_compatible "
            "--base-url http://127.0.0.1:8000/v1 --api-key-env LOCAL_GATEWAY_API_KEY --json"
        )
        status, payload = _post_action(host, port, add_provider)
        assert status == HTTPStatus.OK, payload
        assert payload["executed"] is True
        assert payload["exit_code"] == 0
        assert (tmp_path / ".devflow/providers/local_gateway.yaml").exists()

        add_model = (
            "devflow agent add-model --provider local_gateway --model local/test-model "
            "--authority advisory --role frontier_planner_architect_reviewer --json"
        )
        status, payload = _post_action(host, port, add_model)
        assert status == HTTPStatus.OK, payload
        assert payload["executed"] is True
        assert payload["exit_code"] == 0
        assert "local_gateway-local-test-model-advisory-frontier_planner_architect_reviewer" in (
            tmp_path / ".devflow/agents/registry.yaml"
        ).read_text(encoding="utf-8")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_operating_layer_blocks_broad_agent_command_but_allows_exact_patch_proposal_attempt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    assert runner.invoke(app, ["init"]).exit_code == 0
    assert runner.invoke(app, ["task", "create", "patch proposal from browser"]).exit_code == 0
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    server, thread, host, port = _serve_operating_layer(tmp_path)
    try:
        broad = "devflow agent run local-gemma4-qat --prompt hello --json"
        status, payload = _post_action(host, port, broad)
        assert status == HTTPStatus.CONFLICT, payload
        assert payload["executed"] is False

        exact = "devflow agent propose-patch --task task-0001 --profile test-patch-proposal-surface --json"
        status, payload = _post_action(host, port, exact)
        assert status == HTTPStatus.OK, payload
        assert payload["executed"] is True
        assert payload["exit_code"] != 0
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_operating_layer_server_runs_approved_task_creation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    command = (
        'devflow task create --definition-of-done '
        '"Launchpad can start this task after creation." "browser created task"'
    )
    server, thread, host, port = _serve_operating_layer(tmp_path)
    try:
        status, payload = _post_action(host, port, command)

        assert status == HTTPStatus.OK
        assert payload["executed"] is True
        assert payload["requires_human_approval"] is True
        assert payload["classification"]["safety_class"] == "approval_required_task_state"
        assert payload["exit_code"] == 0
        assert "Created task-0001: browser created task" in payload["stdout"]
        task_yaml = (tmp_path / ".devflow" / "tasks" / "task-0001" / "task.yaml").read_text(encoding="utf-8")
        summary = json.loads((tmp_path / ".devflow" / "tasks" / "task-0001" / "summary.json").read_text())
        assert 'definition_of_done: "Launchpad can start this task after creation."' in task_yaml
        assert summary["definition_of_done"] == "Launchpad can start this task after creation."
        assert not (tmp_path / ".devflow" / "worktrees").exists()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_operating_layer_server_runs_approved_task_close(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    assert runner.invoke(app, ["task", "create", "browser close target"]).exit_code == 0
    command = 'devflow task close task-0001 --outcome abandoned --reason "operator cleared stale task"'
    server, thread, host, port = _serve_operating_layer(tmp_path)
    try:
        status, payload = _post_action(host, port, command)

        assert status == HTTPStatus.OK
        assert payload["executed"] is True
        assert payload["requires_human_approval"] is True
        assert payload["classification"]["safety_class"] == "approval_required_task_state"
        assert payload["exit_code"] == 0
        assert "closed: yes" in payload["stdout"]
        closure = json.loads((tmp_path / ".devflow" / "tasks" / "task-0001" / "closure.json").read_text())
        assert closure["outcome"] == "abandoned"
        assert closure["reason"] == "operator cleared stale task"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_operating_layer_server_runs_approved_cleanup_preview(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    assert runner.invoke(app, ["task", "create", "browser cleanup preview"]).exit_code == 0
    assert runner.invoke(
        app,
        ["task", "close", "task-0001", "--outcome", "abandoned", "--reason", "preview cleanup"],
    ).exit_code == 0
    command = "devflow task cleanup task-0001 --preview"
    server, thread, host, port = _serve_operating_layer(tmp_path)
    try:
        status, payload = _post_action(host, port, command)

        assert status == HTTPStatus.OK
        assert payload["executed"] is True
        assert payload["requires_human_approval"] is True
        assert payload["classification"]["safety_class"] == "approval_required_task_state"
        assert payload["exit_code"] == 0
        assert "mode: preview" in payload["stdout"]
        assert (tmp_path / ".devflow" / "workspaces" / "task-0001").exists()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_operating_layer_server_runs_approved_idea_classify(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    capture_idea(tmp_path, "Turn this rough thought into a scoped candidate.", title="Candidate seed")
    command = 'devflow idea classify I-0001 --maturity candidate --note "clear next step"'
    server, thread, host, port = _serve_operating_layer(tmp_path)
    try:
        status, payload = _post_action(host, port, command)

        assert status == HTTPStatus.OK
        assert payload["executed"] is True
        assert payload["requires_human_approval"] is True
        assert payload["classification"]["safety_class"] == "approval_required_evidence_writing"
        assert payload["exit_code"] == 0
        assert "idea_id: I-0001" in payload["stdout"]
        assert "maturity: candidate" in payload["stdout"]
        idea_path = tmp_path / ".devflow" / "ideas" / "I-0001"
        metadata = json.loads((idea_path / "idea.json").read_text(encoding="utf-8"))
        assert metadata["status"] == "classified"
        assert metadata["maturity"] == "candidate"
        assert "clear next step" in (idea_path / "classification.md").read_text(encoding="utf-8")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_operating_layer_server_runs_approved_idea_capture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    command = 'devflow idea capture --source browser --title "Better intake" "Let me dump rough project brainstorms before tasking."'
    server, thread, host, port = _serve_operating_layer(tmp_path)
    try:
        status, payload = _post_action(host, port, command)

        assert status == HTTPStatus.OK
        assert payload["executed"] is True
        assert payload["requires_human_approval"] is True
        assert payload["classification"]["safety_class"] == "approval_required_evidence_writing"
        assert payload["exit_code"] == 0
        assert "idea_id: I-0001" in payload["stdout"]
        assert "created_task: no" in payload["stdout"]
        idea_path = tmp_path / ".devflow" / "ideas" / "I-0001"
        assert (idea_path / "idea.json").exists()
        assert "rough project brainstorms" in (idea_path / "raw.md").read_text(encoding="utf-8")
        assert not (tmp_path / ".devflow" / "tasks" / "task-0001").exists()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_operating_layer_server_runs_approved_idea_park(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    capture_idea(tmp_path, "Save this for later.", title="Later idea")
    command = 'devflow idea park I-0001 --reason "not this week"'
    server, thread, host, port = _serve_operating_layer(tmp_path)
    try:
        status, payload = _post_action(host, port, command)

        assert status == HTTPStatus.OK
        assert payload["executed"] is True
        assert payload["requires_human_approval"] is True
        assert payload["classification"]["safety_class"] == "approval_required_evidence_writing"
        assert payload["exit_code"] == 0
        assert "idea_id: I-0001" in payload["stdout"]
        assert "status: parked" in payload["stdout"]
        metadata = json.loads((tmp_path / ".devflow" / "ideas" / "I-0001" / "idea.json").read_text())
        assert metadata["status"] == "parked"
        assert metadata["park_reason"] == "not this week"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_operating_layer_server_action_run_resolver_errors_return_stable_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    server, thread, host, port = _serve_operating_layer(tmp_path)
    try:
        monkeypatch.setattr(
            actions_agents_handlers,
            "resolve_browser_action_command",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError("resolver failure")),
        )
        status, payload = _post_action(host, port, 'devflow idea capture "resolver-only"')
        assert status == HTTPStatus.BAD_REQUEST
        assert payload["error"] == "resolver failure"
        assert payload["error_code"] == "resolver_failure"
        assert payload["error_type"] == "ValueError"
        assert payload["retriable"] is False
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_operating_layer_server_action_run_file_not_found_is_stable_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    server, thread, host, port = _serve_operating_layer(tmp_path)
    try:
        monkeypatch.setattr(
            operating_layer_server.subprocess,
            "run",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(FileNotFoundError("no-such-command")),
        )
        status, payload = _post_action(host, port, 'devflow idea capture "missing executable"')
        assert status == HTTPStatus.INTERNAL_SERVER_ERROR
        assert payload["error_code"] == "command_execution_failed"
        assert payload["error_type"] == "FileNotFoundError"
        assert payload["error"].startswith("failed to execute command:")
        assert payload["retriable"] is True
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_operating_layer_server_action_run_os_error_is_stable_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    server, thread, host, port = _serve_operating_layer(tmp_path)
    try:
        monkeypatch.setattr(
            operating_layer_server.subprocess,
            "run",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError(13, "permission denied")),
        )
        status, payload = _post_action(host, port, 'devflow idea capture "os error"')
        assert status == HTTPStatus.INTERNAL_SERVER_ERROR
        assert payload["error_code"] == "command_execution_failed"
        assert payload["error_type"] == "PermissionError"
        assert "failed to execute command" in payload["error"]
        assert payload["retriable"] is True
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_operating_layer_server_action_run_timeout_is_stable_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    server, thread, host, port = _serve_operating_layer(tmp_path)
    try:
        monkeypatch.setattr(
            operating_layer_server.subprocess,
            "run",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                subprocess.TimeoutExpired(
                    cmd=["devflow", "idea", "capture"],
                    timeout=operating_layer_server.ACTION_TIMEOUT_SECONDS,
                    output="partial stdout",
                    stderr="partial stderr",
                )
            ),
        )
        status, payload = _post_action(host, port, 'devflow idea capture "timeout"')
        assert status == HTTPStatus.REQUEST_TIMEOUT
        assert payload["error"] == f"command timed out after {operating_layer_server.ACTION_TIMEOUT_SECONDS}s"
        assert payload["error_code"] == "command_timed_out"
        assert payload["error_type"] == "TimeoutExpired"
        assert payload["retriable"] is True
        assert payload["executed"] is True
        assert payload["timed_out"] is True
        assert payload["exit_code"] is None
        assert payload["stdout"] == "partial stdout"
        assert payload["stderr"] == "partial stderr"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
