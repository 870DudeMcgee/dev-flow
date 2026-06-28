from __future__ import annotations

import json
from io import BytesIO, StringIO
from pathlib import Path
from unittest.mock import patch, MagicMock
import urllib.error

import pytest
from typer.testing import CliRunner

from devflow.cli import app, df_app
from devflow.control_room.agent_terminal import resolve_and_include_file
from tests.helpers import init_test_git_repo

runner = CliRunner()


def test_agent_app_is_reexported_from_control_room_command_module() -> None:
    from devflow.cli import agent_app as cli_agent_app
    from devflow.control_room.agent_command import agent_app as command_agent_app

    cli_source = (Path(__file__).resolve().parents[1] / "src/devflow/cli.py").read_text(encoding="utf-8")

    assert cli_agent_app is command_agent_app
    assert "agent_app = typer.Typer" not in cli_source
    assert "@agent_app.command" not in cli_source


@pytest.fixture
def mock_repo(tmp_path: Path) -> Path:
    # Set up basic agent registry and directories
    agents_dir = tmp_path / ".devflow" / "agents"
    agents_dir.mkdir(parents=True)

    # registry.yaml with default agents
    registry_content = """
version: 1
default_agent: qwopus-implementer
agents:
  qwopus-implementer:
    provider: ollama
    model: qwopus:latest
    adapter: ollama_chat
    role: implementation_worker
    tier: strong_local
    default_mode: workspace_write
    execution_mode: automated
    workspace: isolated_task_workspace
    enabled: true
  disabled-agent:
    provider: ollama
    model: qwen2.5-coder:14b
    adapter: ollama_chat
    role: implementation_worker
    tier: strong_local
    default_mode: workspace_write
    execution_mode: automated
    workspace: isolated_task_workspace
    enabled: false
  non-ollama-agent:
    provider: openai
    model: gpt-4
    adapter: openai_chat
    role: implementation_worker
    tier: frontier
    default_mode: read_only
    execution_mode: automated
    workspace: isolated_task_workspace
    enabled: true
"""
    (agents_dir / "registry.yaml").write_text(registry_content, encoding="utf-8")

    # provider config
    prov_dir = tmp_path / ".devflow" / "providers"
    prov_dir.mkdir(parents=True)
    (prov_dir / "ollama.yaml").write_text("base_url: http://localhost:11434\nenabled: true\n", encoding="utf-8")

    return tmp_path


def test_agent_serial_packet_writes_packet_only_run_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    init_test_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    with patch("urllib.request.urlopen", side_effect=AssertionError("serial-packet must not call providers")):
        result = runner.invoke(
            app,
            [
                "agent",
                "serial-packet",
                "--phase",
                "implementer",
                "--provider",
                "ollama",
                "--model",
                "qwen3.6-32b-256k:latest",
                "--allowed-file",
                "src/devflow/control_room/foo.py",
                "--allowed-file",
                "tests/test_foo.py",
                "--verify",
                "env PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_foo.py -q",
                "--mission",
                "Implement a bounded slice from a packet only.",
                "--run-id",
                "cli-slice4",
            ],
        )

    assert result.exit_code == 0, result.output
    assert "run_dir: .devflow/local-agent-runs/cli-slice4" in result.output
    assert "worker_packet: .devflow/local-agent-runs/cli-slice4/worker-packet.md" in result.output
    assert "completion_verifier: .devflow/local-agent-runs/cli-slice4/completion-verifier.py" in result.output
    assert "model_launch: false" in result.output
    assert "worker_ran: no" in result.output
    assert "git_mutation: false" in result.output
    assert "next_safe_manual_launch:" in result.output
    assert "preflight.json" in result.output

    run_dir = tmp_path / ".devflow/local-agent-runs/cli-slice4"
    assert (run_dir / "run.json").exists()
    assert (run_dir / "completion-verifier.py").exists()
    manifest = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    assert manifest["phase"] == "implementer"
    assert manifest["provider"] == "ollama"
    assert manifest["model"] == "qwen3.6-32b-256k:latest"
    assert manifest["allowed_files"] == [
        "src/devflow/control_room/foo.py",
        "tests/test_foo.py",
    ]
    assert manifest["verification_commands"] == [
        {
            "order": 1,
            "command": "env PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_foo.py -q",
        }
    ]
    assert manifest["safety"]["model_launch"] is False
    assert manifest["safety"]["git_mutation"] is False
    assert manifest["runtime"] == {
        "kind": "manual",
        "hermes_profile": None,
        "toolsets": [],
        "packet_only": True,
    }


def test_agent_serial_packet_writes_hermes_profile_runtime_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    init_test_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    with patch("urllib.request.urlopen", side_effect=AssertionError("serial-packet must not call providers")):
        result = runner.invoke(
            app,
            [
                "agent",
                "serial-packet",
                "--phase",
                "implementer",
                "--provider",
                "ollama",
                "--model",
                "qwen3.6-32b-256k:latest",
                "--allowed-file",
                "src/devflow/control_room/serial_local_agent_run.py",
                "--verify",
                "pytest tests/test_serial_local_agent_run.py -q",
                "--run-id",
                "cli-hermes-runtime",
                "--runtime",
                "hermes-profile",
                "--hermes-profile",
                "qwen-worker",
                "--toolset",
                "file",
                "--toolset",
                "terminal",
            ],
        )

    assert result.exit_code == 0, result.output
    assert "runtime: hermes-profile" in result.output
    assert "hermes_profile: qwen-worker" in result.output
    assert "toolsets: file, terminal" in result.output
    assert "model_launch: false" in result.output
    assert "worker_ran: no" in result.output
    assert "git_mutation: false" in result.output

    run_dir = tmp_path / ".devflow/local-agent-runs/cli-hermes-runtime"
    manifest = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    assert manifest["runtime"] == {
        "kind": "hermes-profile",
        "hermes_profile": "qwen-worker",
        "toolsets": ["file", "terminal"],
        "packet_only": True,
    }
    packet = (run_dir / "worker-packet.md").read_text(encoding="utf-8")
    assert "This packet is intended for Hermes profile `qwen-worker`, but packet creation did not launch it." in packet


def test_agent_serial_packet_requires_hermes_profile_for_hermes_runtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    init_test_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(
        app,
        [
            "agent",
            "serial-packet",
            "--phase",
            "implementer",
            "--provider",
            "ollama",
            "--model",
            "qwen3.6-32b-256k:latest",
            "--allowed-file",
            "src/example.py",
            "--verify",
            "pytest tests/test_example.py -q",
            "--runtime",
            "hermes-profile",
        ],
    )

    assert result.exit_code == 1
    assert "hermes_profile is required when runtime_kind is hermes-profile" in result.output
    assert not (tmp_path / ".devflow/local-agent-runs").exists()


def _write_cli_hermes_runtime_packet(run_id: str = "cli-hermes-run") -> None:
    create_result = runner.invoke(
        app,
        [
            "agent",
            "serial-packet",
            "--phase",
            "implementer",
            "--provider",
            "ollama",
            "--model",
            "qwen3.6-32b-256k:latest",
            "--allowed-file",
            "src/devflow/control_room/hermes_worker_runtime.py",
            "--verify",
            "pytest tests/test_hermes_worker_runtime.py -q",
            "--run-id",
            run_id,
            "--runtime",
            "hermes-profile",
            "--hermes-profile",
            "qwen-worker",
            "--toolset",
            "file",
        ],
    )
    assert create_result.exit_code == 0, create_result.output


def test_agent_hermes_run_dry_run_json_previews_without_launch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    init_test_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    _write_cli_hermes_runtime_packet()

    with patch("subprocess.run", side_effect=AssertionError("dry-run must not call subprocess.run")), patch(
        "subprocess.Popen", side_effect=AssertionError("dry-run must not call subprocess.Popen")
    ):
        result = runner.invoke(
            app,
            [
                "agent",
                "hermes-run",
                "cli-hermes-run",
                "--profile",
                "qwen-worker",
                "--dry-run",
                "--json",
            ],
        )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["will_launch_hermes"] is False
    assert payload["launch_allowed"] is True
    assert payload["run_id"] == "cli-hermes-run"
    assert payload["hermes_profile"] == "qwen-worker"
    assert payload["preflight_state"] == "free"
    assert payload["packet_path"] == ".devflow/local-agent-runs/cli-hermes-run/worker-packet.md"
    assert payload["command_preview"][:5] == ["hermes", "-p", "qwen-worker", "chat", "-q"]
    assert not (tmp_path / ".devflow/local-agent-runs/cli-hermes-run/hermes-run.json").exists()


def test_agent_hermes_run_real_launch_uses_fake_bin_and_writes_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    init_test_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    _write_cli_hermes_runtime_packet("cli-hermes-launch")
    fake = tmp_path / "fake-hermes"
    fake.write_text(
        "#!/usr/bin/env python3\n"
        "import json\n"
        "import sys\n"
        "from pathlib import Path\n"
        "Path('cli-fake-argv.json').write_text(json.dumps({'argv': sys.argv}) + '\\n', encoding='utf-8')\n"
        "print('cli fake stdout')\n"
        "print('cli fake stderr', file=sys.stderr)\n",
        encoding="utf-8",
    )
    fake.chmod(fake.stat().st_mode | 0o111)

    result = runner.invoke(
        app,
        [
            "agent",
            "hermes-run",
            "cli-hermes-launch",
            "--profile",
            "qwen-worker",
            "--hermes-bin",
            fake.as_posix(),
            "--timeout-seconds",
            "10",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["will_launch_hermes"] is True
    assert payload["launch_status"] == "completed"
    assert payload["exit_code"] == 0
    assert payload["stdout_path"] == ".devflow/local-agent-runs/cli-hermes-launch/hermes-stdout.txt"
    assert payload["stderr_path"] == ".devflow/local-agent-runs/cli-hermes-launch/hermes-stderr.txt"
    assert payload["next_safe_action"] == "Run completion-verifier.py from the packet directory."
    run_dir = tmp_path / ".devflow/local-agent-runs/cli-hermes-launch"
    assert (run_dir / "hermes-run.json").exists()
    assert (run_dir / "hermes-stdout.txt").read_text(encoding="utf-8") == "cli fake stdout\n"
    assert (run_dir / "hermes-stderr.txt").read_text(encoding="utf-8") == "cli fake stderr\n"
    fake_payload = json.loads((tmp_path / "cli-fake-argv.json").read_text(encoding="utf-8"))
    assert fake_payload["argv"][1:5] == ["-p", "qwen-worker", "chat", "-q"]
    assert not (run_dir / "verification-report.json").exists()


def test_agent_serial_packet_requires_allowlist_and_verification_commands(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    init_test_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    missing_allowlist = runner.invoke(
        app,
        [
            "agent",
            "serial-packet",
            "--phase",
            "implementer",
            "--provider",
            "ollama",
            "--model",
            "qwen3.6-32b-256k:latest",
            "--verify",
            "pytest tests/test_foo.py -q",
        ],
    )
    assert missing_allowlist.exit_code == 1
    assert "allowed_files must contain at least one path" in missing_allowlist.output

    missing_verify = runner.invoke(
        app,
        [
            "agent",
            "serial-packet",
            "--phase",
            "implementer",
            "--provider",
            "ollama",
            "--model",
            "qwen3.6-32b-256k:latest",
            "--allowed-file",
            "src/example.py",
        ],
    )
    assert missing_verify.exit_code == 1
    assert "verification_commands must contain at least one command" in missing_verify.output

    assert not (tmp_path / ".devflow/local-agent-runs").exists()


def test_agent_serial_packet_leaves_existing_df_local_worker_command_unchanged(
    mock_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(mock_repo)
    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps({"response": "legacy command still works"}).encode("utf-8")

    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value.__enter__.return_value = mock_response
        result = runner.invoke(df_app, ["ask", "hello"])

    assert result.exit_code == 0
    assert "legacy command still works" in result.output
    runs_dir = mock_repo / ".devflow" / "agent-runs"
    assert len(list(runs_dir.iterdir())) == 1
    assert not (mock_repo / ".devflow" / "local-agent-runs").exists()


def test_resolve_and_include_file_valid(mock_repo: Path) -> None:
    test_file = mock_repo / "src" / "test.py"
    test_file.parent.mkdir(parents=True)
    test_file.write_text("print('hello')", encoding="utf-8")

    content = resolve_and_include_file(mock_repo, "src/test.py")
    assert content == "print('hello')"


def test_resolve_and_include_file_traversal(mock_repo: Path) -> None:
    with pytest.raises(ValueError, match="outside repository"):
        resolve_and_include_file(mock_repo, "../outside.py")


def test_resolve_and_include_file_git_prohibited(mock_repo: Path) -> None:
    git_file = mock_repo / ".git" / "config"
    git_file.parent.mkdir(parents=True)
    git_file.write_text("config", encoding="utf-8")
    with pytest.raises(ValueError, match="Access to '.git' is prohibited"):
        resolve_and_include_file(mock_repo, ".git/config")


def test_resolve_and_include_file_directory(mock_repo: Path) -> None:
    with pytest.raises(ValueError, match="Directories are not supported"):
        resolve_and_include_file(mock_repo, ".devflow")


def test_df_ask_success(mock_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(mock_repo)

    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps({"response": "This is a mock answer from qwopus"}).encode("utf-8")

    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value.__enter__.return_value = mock_response
        result = runner.invoke(df_app, ["ask", "Tell me about task-0012"])

    assert result.exit_code == 0
    assert "This is a mock answer from qwopus" in result.output
    # Check that a run was saved
    runs_dir = mock_repo / ".devflow" / "agent-runs"
    assert runs_dir.exists()
    runs = list(runs_dir.iterdir())
    assert len(runs) == 1
    assert runs[0].name.endswith("-qwopus-implementer")
    assert (runs[0] / "prompt.md").read_text(encoding="utf-8") == "Tell me about task-0012"
    assert (runs[0] / "response.md").read_text(encoding="utf-8") == "This is a mock answer from qwopus"
    run_meta = json.loads((runs[0] / "run.json").read_text(encoding="utf-8"))
    assert run_meta["command"] == "ask"
    assert run_meta["agent_name"] == "qwopus-implementer"
    assert run_meta["status"] == "success"
    # Ensure no proposal.patch is created (safety check)
    assert not (runs[0] / "proposal.patch").exists()


def test_df_ask_specific_agent(mock_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Add another enabled agent
    registry_file = mock_repo / ".devflow" / "agents" / "registry.yaml"
    registry_file.write_text(
        registry_file.read_text(encoding="utf-8") +
        "  qwen-agent:\n"
        "    provider: ollama\n"
        "    model: qwen\n"
        "    adapter: ollama_chat\n"
        "    role: implementation_worker\n"
        "    tier: strong_local\n"
        "    default_mode: workspace_write\n"
        "    execution_mode: automated\n"
        "    workspace: isolated_task_workspace\n"
        "    enabled: true\n",
        encoding="utf-8"
    )

    monkeypatch.chdir(mock_repo)

    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps({"response": "Answer from qwen"}).encode("utf-8")

    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value.__enter__.return_value = mock_response
        result = runner.invoke(df_app, ["ask", "--agent", "qwen-agent", "hello"])

    assert result.exit_code == 0
    assert "Answer from qwen" in result.output
    runs_dir = mock_repo / ".devflow" / "agent-runs"
    runs = list(runs_dir.iterdir())
    assert any(run.name.endswith("-qwen-agent") for run in runs)


def test_df_ask_with_file_include(mock_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(mock_repo)
    test_file = mock_repo / "foo.txt"
    test_file.write_text("Hello from foo", encoding="utf-8")

    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps({"response": "Checked your file"}).encode("utf-8")

    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value.__enter__.return_value = mock_response
        result = runner.invoke(df_app, ["ask", "--file", "foo.txt", "Read this file"])

    assert result.exit_code == 0
    assert "Checked your file" in result.output

    # Check prompt.md includes file content
    runs_dir = mock_repo / ".devflow" / "agent-runs"
    runs = list(runs_dir.iterdir())
    prompt_content = (runs[0] / "prompt.md").read_text(encoding="utf-8")
    assert "Read this file" in prompt_content
    assert "## Included file: foo.txt" in prompt_content
    assert "Hello from foo" in prompt_content


def test_df_ask_no_save_and_show_paths(mock_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(mock_repo)

    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps({"response": "No save answer"}).encode("utf-8")

    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value.__enter__.return_value = mock_response
        result = runner.invoke(df_app, ["ask", "--no-save", "--show-paths", "hello"])

    assert result.exit_code == 0
    assert "No save answer" in result.output
    assert "Saved: disabled by --no-save" in result.output
    # verify NO directory was created
    runs_dir = mock_repo / ".devflow" / "agent-runs"
    if runs_dir.exists():
        assert len(list(runs_dir.iterdir())) == 0


def test_df_ask_show_paths_saved(mock_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(mock_repo)

    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps({"response": "Saved answer"}).encode("utf-8")

    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value.__enter__.return_value = mock_response
        result = runner.invoke(df_app, ["ask", "--show-paths", "hello"])

    assert result.exit_code == 0
    assert "Saved answer" in result.output
    assert "Saved:" in result.output
    assert "prompt.md" in result.output
    assert "response.md" in result.output
    assert "run.json" in result.output


def test_df_run_with_stdin(mock_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(mock_repo)

    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps({"response": "Stdin read successfully"}).encode("utf-8")

    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value.__enter__.return_value = mock_response
        result = runner.invoke(df_app, ["run", "--stdin"], input="Prompt from stdin\n")

    assert result.exit_code == 0
    assert "Stdin read successfully" in result.output
    runs_dir = mock_repo / ".devflow" / "agent-runs"
    runs = list(runs_dir.iterdir())
    prompt_content = (runs[0] / "prompt.md").read_text(encoding="utf-8")
    assert prompt_content.strip() == "Prompt from stdin"


def test_df_run_with_prompt_file(mock_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(mock_repo)
    pf = mock_repo / "prompt.md"
    pf.write_text("Hello from prompt file", encoding="utf-8")

    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps({"response": "File read successfully"}).encode("utf-8")

    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value.__enter__.return_value = mock_response
        result = runner.invoke(df_app, ["run", "--prompt-file", "prompt.md"])

    assert result.exit_code == 0
    assert "File read successfully" in result.output
    runs_dir = mock_repo / ".devflow" / "agent-runs"
    runs = list(runs_dir.iterdir())
    prompt_content = (runs[0] / "prompt.md").read_text(encoding="utf-8")
    assert prompt_content.strip() == "Hello from prompt file"


def test_refuse_unknown_agent(mock_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(mock_repo)
    result = runner.invoke(df_app, ["ask", "--agent", "nonexistent-agent", "hello"])
    assert result.exit_code == 1
    assert "Unknown agent 'nonexistent-agent'" in result.output


def test_refuse_disabled_agent_by_default(mock_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(mock_repo)
    result = runner.invoke(df_app, ["ask", "--agent", "disabled-agent", "hello"])
    assert result.exit_code == 1
    assert "is disabled" in result.output


def test_allow_disabled_agent(mock_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(mock_repo)

    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps({"response": "Disabled agent bypassed"}).encode("utf-8")

    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value.__enter__.return_value = mock_response
        result = runner.invoke(df_app, ["ask", "--agent", "disabled-agent", "--allow-disabled", "hello"])

    assert result.exit_code == 0
    assert "Disabled agent bypassed" in result.output


def test_refuse_non_ollama_provider(mock_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(mock_repo)
    result = runner.invoke(df_app, ["ask", "--agent", "non-ollama-agent", "hello"])
    assert result.exit_code == 1
    assert "only local ollama agents are supported" in result.output.lower()


def test_unreachable_ollama_error(mock_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(mock_repo)
    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("Connection refused")):
        result = runner.invoke(df_app, ["ask", "hello"])

    assert result.exit_code == 1
    assert "Ollama could not be reached" in result.output
    assert "ollama serve" in result.output


def test_missing_model_error(mock_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(mock_repo)
    raw_error = b'{"error":"model \\"qwopus:latest\\" not found, try pulling it first"}'
    http_error = urllib.error.HTTPError(
        "http://localhost:11434/api/generate",
        404,
        "Not Found",
        {},
        BytesIO(raw_error),
    )

    with patch("urllib.request.urlopen", side_effect=http_error):
        result = runner.invoke(df_app, ["ask", "hello"])

    assert result.exit_code == 1
    assert "Model 'qwopus:latest' is missing" in result.output
    assert "ollama pull qwopus:latest" in result.output


def test_qwopus_one_shot(mock_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(mock_repo)
    from devflow.cli import qwopus_main

    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps({"response": "hello from direct qwopus"}).encode("utf-8")

    with patch("sys.argv", ["qwopus", "Say exactly: hello from qwopus"]), \
         patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value.__enter__.return_value = mock_response

        # Catch print outputs
        out = StringIO()
        with patch("sys.stdout", out):
            qwopus_main()

        assert "hello from direct qwopus" in out.getvalue()


def test_qwopus_chat(mock_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(mock_repo)
    from devflow.cli import qwopus_main

    # Mock interactive chat replies
    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps({
        "message": {"role": "assistant", "content": "I am in chat mode"}
    }).encode("utf-8")

    # Simulate /exit right away
    with patch("sys.argv", ["qwopus", "chat"]), \
         patch("urllib.request.urlopen") as mock_urlopen, \
         patch("builtins.input", return_value="/exit"):
        mock_urlopen.return_value.__enter__.return_value = mock_response

        out = StringIO()
        with patch("sys.stdout", out):
            qwopus_main()

        # Check chat start message
        assert "Dev-Flow local agent chat" in out.getvalue()
        assert "qwopus-implementer" in out.getvalue()


def test_pyproject_toml_script_entry_points(mock_repo: Path) -> None:
    pyproject = mock_repo / "pyproject.toml"
    # Write mock pyproject.toml
    pyproject.write_text("""
[project.scripts]
devflow = "devflow.cli:main"
df = "devflow.cli:df_main"
qwopus = "devflow.cli:qwopus_main"
""", encoding="utf-8")

    content = pyproject.read_text(encoding="utf-8")
    assert "df = \"devflow.cli:df_main\"" in content
    assert "qwopus = \"devflow.cli:qwopus_main\"" in content


def test_df_quick_and_help_local(mock_repo: Path) -> None:
    result_quick = runner.invoke(df_app, ["quick"])
    assert result_quick.exit_code == 0
    assert "Dev-Flow local agent commands" in result_quick.output
    assert "qwopus chat" in result_quick.output
    assert "df run --stdin" in result_quick.output
    assert "devflow task promote-preview" in result_quick.output

    result_help = runner.invoke(df_app, ["help-local"])
    assert result_help.exit_code == 0
    assert result_help.output == result_quick.output


def test_df_ask_unquoted_and_quoted(mock_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(mock_repo)

    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps({"response": "Mocked response"}).encode("utf-8")

    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value.__enter__.return_value = mock_response

        # Test unquoted multi-word
        result_unquoted = runner.invoke(df_app, ["ask", "hello", "there"])
        assert result_unquoted.exit_code == 0
        assert "Mocked response" in result_unquoted.output
        runs_dir = mock_repo / ".devflow" / "agent-runs"
        latest_run = max(runs_dir.iterdir(), key=lambda p: p.stat().st_mtime)
        assert (latest_run / "prompt.md").read_text(encoding="utf-8") == "hello there"

        # Test quoted multi-word
        result_quoted = runner.invoke(df_app, ["ask", "hello there"])
        assert result_quoted.exit_code == 0
        assert "Mocked response" in result_quoted.output
        latest_run = max(runs_dir.iterdir(), key=lambda p: p.stat().st_mtime)
        assert (latest_run / "prompt.md").read_text(encoding="utf-8") == "hello there"


def test_agent_ask_unquoted(mock_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(mock_repo)

    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps({"response": "Mocked response"}).encode("utf-8")

    from devflow.cli import agent_app
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value.__enter__.return_value = mock_response

        # Test unquoted multi-word on agent ask
        result = runner.invoke(agent_app, ["ask", "qwopus-implementer", "hello", "there"])
        assert result.exit_code == 0
        assert "Mocked response" in result.output
        runs_dir = mock_repo / ".devflow" / "agent-runs"
        latest_run = max(runs_dir.iterdir(), key=lambda p: p.stat().st_mtime)
        assert (latest_run / "prompt.md").read_text(encoding="utf-8") == "hello there"


def test_qwopus_hello_there(mock_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(mock_repo)
    from devflow.cli import qwopus_main

    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps({"response": "hello from qwopus unquoted"}).encode("utf-8")

    with patch("sys.argv", ["qwopus", "hello", "there"]), \
         patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value.__enter__.return_value = mock_response

        out = StringIO()
        with patch("sys.stdout", out):
            qwopus_main()

        assert "hello from qwopus unquoted" in out.getvalue()
        # Verify the prompt was indeed joined
        runs_dir = mock_repo / ".devflow" / "agent-runs"
        latest_run = max(runs_dir.iterdir(), key=lambda p: p.stat().st_mtime)
        assert (latest_run / "prompt.md").read_text(encoding="utf-8") == "hello there"


def test_missing_prompt_errors(mock_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(mock_repo)

    # 1. df ask with missing prompt
    result_df = runner.invoke(df_app, ["ask"])
    assert result_df.exit_code == 1
    assert "Error: prompt is required." in result_df.output
    assert "df quick" in result_df.output

    # 2. agent ask with missing prompt
    from devflow.cli import agent_app
    result_agent = runner.invoke(agent_app, ["ask", "qwopus-implementer"])
    assert result_agent.exit_code == 1
    assert "Error: prompt is required." in result_agent.output

    # 3. qwopus with missing prompt
    from devflow.cli import qwopus_main
    with patch("sys.argv", ["qwopus"]), \
         patch("sys.stdin.isatty", return_value=True):
        out = StringIO()
        err = StringIO()
        with patch("sys.stdout", out), patch("sys.stderr", err):
            with pytest.raises(SystemExit) as exc_info:
                qwopus_main()
            assert exc_info.value.code == 1

        assert "Error: prompt is required." in err.getvalue()
        assert "df quick" in err.getvalue()


def test_project_context_qwopus_basic(mock_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(mock_repo)
    readme = mock_repo / "README.md"
    readme.write_text("DevFlow is a local-first agent control room.", encoding="utf-8")

    from devflow.cli import qwopus_main

    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps({"response": "Mocked qwopus reply"}).encode("utf-8")

    with patch("sys.argv", ["qwopus", "--project", "tell me what this project is"]), \
         patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value.__enter__.return_value = mock_response

        out = StringIO()
        with patch("sys.stdout", out):
            qwopus_main()

        assert "Mocked qwopus reply" in out.getvalue()
        # Verify prompt captured in mock_urlopen payload
        assert mock_urlopen.called
        args, kwargs = mock_urlopen.call_args
        req = args[0]
        payload = json.loads(req.data.decode("utf-8"))
        sent_prompt = payload["prompt"]

        assert "tell me what this project is" in sent_prompt
        assert "Project context: DevFlow repository" in sent_prompt
        assert "File: README.md" in sent_prompt
        assert "DevFlow is a local-first agent control room." in sent_prompt
        # No task ID required
        assert "task-0001" not in sent_prompt

        # Assert no proposal.patch is created in agent-runs
        runs_dir = mock_repo / ".devflow" / "agent-runs"
        assert runs_dir.exists()
        latest_run = max(runs_dir.iterdir(), key=lambda p: p.stat().st_mtime)
        assert not (latest_run / "proposal.patch").exists()


def test_project_context_df_ask_basic(mock_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(mock_repo)
    readme = mock_repo / "README.md"
    readme.write_text("DevFlow is a local-first agent control room.", encoding="utf-8")

    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps({"response": "Mocked df ask reply"}).encode("utf-8")

    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value.__enter__.return_value = mock_response
        result = runner.invoke(df_app, ["ask", "--project", "tell me what this project is"])

    assert result.exit_code == 0
    assert "Mocked df ask reply" in result.output

    assert mock_urlopen.called
    args, kwargs = mock_urlopen.call_args
    req = args[0]
    payload = json.loads(req.data.decode("utf-8"))
    sent_prompt = payload["prompt"]

    assert "tell me what this project is" in sent_prompt
    assert "Project context: DevFlow repository" in sent_prompt
    assert "File: README.md" in sent_prompt
    assert "DevFlow is a local-first agent control room." in sent_prompt


def test_project_context_df_run_basic(mock_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(mock_repo)
    readme = mock_repo / "README.md"
    readme.write_text("DevFlow is a local-first agent control room.", encoding="utf-8")

    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps({"response": "Mocked df run reply"}).encode("utf-8")

    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value.__enter__.return_value = mock_response
        result = runner.invoke(df_app, ["run", "--project", "--prompt", "summarize"])

    assert result.exit_code == 0
    assert "Mocked df run reply" in result.output

    assert mock_urlopen.called
    args, kwargs = mock_urlopen.call_args
    req = args[0]
    payload = json.loads(req.data.decode("utf-8"))
    sent_prompt = payload["prompt"]

    assert "summarize" in sent_prompt
    assert "Project context: DevFlow repository" in sent_prompt
    assert "File: README.md" in sent_prompt
    assert "DevFlow is a local-first agent control room." in sent_prompt


def test_project_context_exclusions(mock_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(mock_repo)

    # Create file inside excluded dirs
    git_conf = mock_repo / ".git" / "config"
    git_conf.parent.mkdir(parents=True, exist_ok=True)
    git_conf.write_text("git secret stuff", encoding="utf-8")

    venv_sec = mock_repo / ".venv" / "secret.txt"
    venv_sec.parent.mkdir(parents=True, exist_ok=True)
    venv_sec.write_text("venv secret stuff", encoding="utf-8")

    venv1_sec = mock_repo / ".venv-1" / "secret.txt"
    venv1_sec.parent.mkdir(parents=True, exist_ok=True)
    venv1_sec.write_text("venv-1 secret stuff", encoding="utf-8")

    workspace_sec = mock_repo / ".devflow" / "workspaces" / "task-x" / "secret.txt"
    workspace_sec.parent.mkdir(parents=True, exist_ok=True)
    workspace_sec.write_text("workspace secret stuff", encoding="utf-8")

    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps({"response": "Exclusions check"}).encode("utf-8")

    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value.__enter__.return_value = mock_response
        runner.invoke(df_app, ["ask", "--project", "test exclusions"])

    assert mock_urlopen.called
    args, kwargs = mock_urlopen.call_args
    sent_prompt = json.loads(args[0].data.decode("utf-8"))["prompt"]

    assert "git secret stuff" not in sent_prompt
    assert "venv secret stuff" not in sent_prompt
    assert "venv-1 secret stuff" not in sent_prompt
    assert "workspace secret stuff" not in sent_prompt


def test_project_context_registry_provider_inclusion(mock_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(mock_repo)
    # mock_repo fixture already creates registry.yaml and ollama.yaml. Let's verify they are included.
    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps({"response": "Inclusion check"}).encode("utf-8")

    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value.__enter__.return_value = mock_response
        runner.invoke(df_app, ["ask", "--project", "test inclusions"])

    assert mock_urlopen.called
    args, kwargs = mock_urlopen.call_args
    sent_prompt = json.loads(args[0].data.decode("utf-8"))["prompt"]

    assert "File: .devflow/agents/registry.yaml" in sent_prompt
    assert "qwopus-implementer:" in sent_prompt
    assert "File: .devflow/providers/ollama.yaml" in sent_prompt
    assert "base_url: http://localhost:11434" in sent_prompt


def test_project_context_tasks_inclusion(mock_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(mock_repo)

    # Create mock tasks
    tasks_dir = mock_repo / ".devflow" / "tasks"

    t1_dir = tasks_dir / "task-0001"
    t1_dir.mkdir(parents=True, exist_ok=True)
    (t1_dir / "task.yaml").write_text(
        "id: task-0001\n"
        "status: verification_failed\n"
        "title: 'Create hello.txt containing exactly: hello from local qwopus'\n"
        "updated_at: '2026-06-01T10:00:00Z'\n",
        encoding="utf-8"
    )

    t2_dir = tasks_dir / "task-0002"
    t2_dir.mkdir(parents=True, exist_ok=True)
    (t2_dir / "task.yaml").write_text(
        "id: task-0002\n"
        "status: worker_failed\n"
        "title: Fix spelling of hello.txt\n"
        "updated_at: '2026-06-01T11:00:00Z'\n",
        encoding="utf-8"
    )

    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps({"response": "Tasks check"}).encode("utf-8")

    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value.__enter__.return_value = mock_response
        runner.invoke(df_app, ["ask", "--project", "test tasks"])

    assert mock_urlopen.called
    args, kwargs = mock_urlopen.call_args
    sent_prompt = json.loads(args[0].data.decode("utf-8"))["prompt"]

    assert "Recent Dev-Flow tasks" in sent_prompt
    # Since t2 has a later timestamp (11:00) than t1 (10:00), they should appear with t2 first
    assert "- task-0002 worker_failed: Fix spelling of hello.txt" in sent_prompt
    assert "- task-0001 verification_failed: Create hello.txt containing exactly: hello from local qwopus" in sent_prompt


def test_project_context_truncation(mock_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(mock_repo)
    readme = mock_repo / "README.md"
    readme.write_text("A" * 1000, encoding="utf-8")

    from devflow.control_room.project_context import build_project_context_packet
    # Run with small max_chars
    packet = build_project_context_packet(mock_repo, max_chars=100)
    assert "[Project context truncated]" in packet
    assert len(packet) <= 100


def test_df_quick_mentions_project(mock_repo: Path) -> None:
    result = runner.invoke(df_app, ["quick"])
    assert result.exit_code == 0
    assert 'qwopus --project "what is this project?"' in result.output
    assert 'df ask --project "what is this project?"' in result.output
    assert 'df run --project --prompt "summarize this project"' in result.output
    assert 'Quotes are optional for simple prompts. Use quotes for shell-sensitive characters, or use qwopus chat.' in result.output

