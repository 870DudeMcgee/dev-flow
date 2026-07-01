from __future__ import annotations

import json
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

from devflow.control_room.local_model_runtime_lock import (
    local_model_lock_dir,
    local_model_runtime_lock,
)
from devflow.control_room.serial_local_agent_run import (
    SerialLocalAgentRunError,
    create_serial_local_agent_run,
    derive_serial_local_run_id,
    serial_local_agent_run_snapshot,
    serial_local_run_dir,
)
from tests.helpers import init_test_git_repo, setup_temp_git_repo


def _python_command(code: str) -> str:
    return f"{shlex.quote(sys.executable)} -c {shlex.quote(code)}"


def _run_completion_verifier(run_dir: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(run_dir / "completion-verifier.py")],
        cwd=run_dir.parent.parent.parent,
        capture_output=True,
        text=True,
        check=False,
    )


def test_serial_local_run_writes_packet_contract(tmp_path: Path) -> None:
    setup_temp_git_repo(tmp_path)
    (tmp_path / "README.md").write_text("# Test Repo\n\nDirty change.\n", encoding="utf-8")
    (tmp_path / "untracked.txt").write_text("untracked\n", encoding="utf-8")
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()

    result = create_serial_local_agent_run(
        tmp_path,
        run_id="slice1-contract",
        phase="implementer",
        provider="ollama",
        model="qwen3.6-32b-256k:latest",
        mission="Implement Slice 1 packet contract only.",
        allowed_files=[
            "src/devflow/control_room/serial_local_agent_run.py",
            "tests/test_serial_local_agent_run.py",
        ],
        verification_commands=[
            "env PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_serial_local_agent_run.py -q",
        ],
        non_goals=["no git stage/commit/push", "no local model launch"],
    )

    run_dir = tmp_path / ".devflow" / "local-agent-runs" / "slice1-contract"
    assert result.run_dir == run_dir
    assert serial_local_run_dir(tmp_path, "slice1-contract") == run_dir
    assert sorted(path.name for path in run_dir.iterdir()) == [
        "allowlist.txt",
        "completion-verifier.py",
        "non-goals.txt",
        "preflight.json",
        "run.json",
        "verification-commands.json",
        "worker-packet.md",
    ]

    manifest = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == 1
    assert manifest["run_id"] == "slice1-contract"
    assert manifest["phase"] == "implementer"
    assert manifest["state"] == "pending"
    assert manifest["provider"] == "ollama"
    assert manifest["model"] == "qwen3.6-32b-256k:latest"
    assert manifest["allowed_files"] == [
        "src/devflow/control_room/serial_local_agent_run.py",
        "tests/test_serial_local_agent_run.py",
    ]
    assert manifest["verification_commands"] == [
        {
            "order": 1,
            "command": "env PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_serial_local_agent_run.py -q",
        }
    ]
    assert manifest["git"]["baseline"]["branch"] == "main"
    assert manifest["git"]["baseline"]["head_sha"] == head
    assert manifest["git"]["dirty_state"]["dirty"] is True
    assert manifest["safety"] == {
        "packet_only": True,
        "model_launch": False,
        "git_mutation": False,
        "promotion": False,
    }

    assert (run_dir / "allowlist.txt").read_text(encoding="utf-8") == (
        "src/devflow/control_room/serial_local_agent_run.py\n"
        "tests/test_serial_local_agent_run.py\n"
    )
    assert json.loads((run_dir / "verification-commands.json").read_text(encoding="utf-8")) == {
        "schema_version": 1,
        "run_id": "slice1-contract",
        "commands": [
            {
                "order": 1,
                "command": "env PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_serial_local_agent_run.py -q",
            }
        ],
    }
    packet = (run_dir / "worker-packet.md").read_text(encoding="utf-8")
    assert "# Serial Local-Agent Packet: implementer" in packet
    assert "## Mission\nImplement Slice 1 packet contract only." in packet
    assert "- src/devflow/control_room/serial_local_agent_run.py" in packet
    assert "- no local model launch" in packet
    assert "```bash" in packet
    assert "pytest tests/test_serial_local_agent_run.py -q" in packet

    status = subprocess.run(
        ["git", "status", "--porcelain=v1", "-uall"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert not any(line.startswith(("A ", "M ", "D ")) for line in status.splitlines())


def test_serial_local_run_defaults_to_manual_runtime_metadata(tmp_path: Path) -> None:
    setup_temp_git_repo(tmp_path)

    result = create_serial_local_agent_run(
        tmp_path,
        run_id="manual-runtime",
        phase="implementer",
        provider="ollama",
        model="qwen3.6-32b-256k:latest",
        allowed_files=["src/example.py"],
        verification_commands=["pytest tests/test_example.py -q"],
    )

    runtime = result.manifest["runtime"]
    assert runtime == {
        "kind": "manual",
        "hermes_profile": None,
        "toolsets": [],
        "packet_only": True,
    }
    assert result.manifest["safety"]["model_launch"] is False
    assert result.manifest["safety"]["git_mutation"] is False
    packet = (result.run_dir / "worker-packet.md").read_text(encoding="utf-8")
    assert "- runtime kind: `manual`" in packet
    assert "Packet creation did not launch Hermes, a local model, or a worker." in packet


def test_serial_local_run_records_hermes_profile_runtime_metadata(tmp_path: Path) -> None:
    setup_temp_git_repo(tmp_path)

    result = create_serial_local_agent_run(
        tmp_path,
        run_id="hermes-runtime",
        phase="implementer",
        provider="ollama",
        model="qwen3.6-32b-256k:latest",
        allowed_files=["src/devflow/control_room/serial_local_agent_run.py"],
        verification_commands=["pytest tests/test_serial_local_agent_run.py -q"],
        runtime_kind="hermes-profile",
        hermes_profile="qwen-worker",
        toolsets=["file", "terminal", "search"],
    )

    runtime = result.manifest["runtime"]
    assert runtime == {
        "kind": "hermes-profile",
        "hermes_profile": "hermes-qwen32-latest",
        "toolsets": ["file", "terminal", "search"],
        "packet_only": True,
    }
    assert result.manifest["safety"]["packet_only"] is True
    assert result.manifest["safety"]["model_launch"] is False
    assert result.manifest["safety"]["git_mutation"] is False
    packet = (result.run_dir / "worker-packet.md").read_text(encoding="utf-8")
    assert "This packet is intended for Hermes profile `hermes-qwen32-latest`, but packet creation did not launch it." in packet
    assert "- toolsets: `file`, `terminal`, `search`" in packet


def test_serial_local_run_requires_profile_for_hermes_runtime(tmp_path: Path) -> None:
    setup_temp_git_repo(tmp_path)

    with pytest.raises(SerialLocalAgentRunError, match="hermes_profile is required when runtime_kind is hermes-profile"):
        create_serial_local_agent_run(
            tmp_path,
            phase="implementer",
            provider="ollama",
            model="qwen3.6-32b-256k:latest",
            allowed_files=["src/example.py"],
            verification_commands=["pytest tests/test_example.py -q"],
            runtime_kind="hermes-profile",
        )


def test_serial_local_run_snapshot_projects_successful_hermes_launch(tmp_path: Path) -> None:
    setup_temp_git_repo(tmp_path)
    result = create_serial_local_agent_run(
        tmp_path,
        run_id="launched-hermes",
        phase="implementer",
        provider="ollama",
        model="qwen3.6-32b-256k:latest",
        allowed_files=["src/example.py"],
        verification_commands=["pytest tests/test_example.py -q"],
        runtime_kind="hermes-profile",
        hermes_profile="qwen-worker",
        toolsets=["file", "terminal"],
    )
    (result.run_dir / "hermes-stdout.txt").write_text("worker output\n", encoding="utf-8")
    (result.run_dir / "hermes-stderr.txt").write_text("", encoding="utf-8")
    (result.run_dir / "hermes-run.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "will_launch_hermes": True,
                "dry_run": False,
                "run_id": "launched-hermes",
                "run_dir": ".devflow/local-agent-runs/launched-hermes",
                "packet_path": ".devflow/local-agent-runs/launched-hermes/worker-packet.md",
                "hermes_profile": "hermes-qwen32-latest",
                "runtime_kind": "hermes-profile",
                "launch_status": "completed",
                "exit_code": 0,
                "stdout_path": ".devflow/local-agent-runs/launched-hermes/hermes-stdout.txt",
                "stderr_path": ".devflow/local-agent-runs/launched-hermes/hermes-stderr.txt",
                "hermes_run_path": ".devflow/local-agent-runs/launched-hermes/hermes-run.json",
                "verification_ran": False,
                "next_safe_action": "Run completion-verifier.py from the packet directory.",
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    snapshot = serial_local_agent_run_snapshot(tmp_path)

    assert snapshot["status"] == "ready_for_verifier"
    assert snapshot["run_state"] == "ready_for_verifier"
    assert snapshot["status_source"] == "hermes_run"
    assert snapshot["runtime_kind"] == "hermes-profile"
    assert snapshot["hermes_profile"] == "hermes-qwen32-latest"
    assert snapshot["launch_status"] == "completed"
    assert snapshot["exit_code"] == 0
    assert snapshot["browser_actions"] == []
    assert snapshot["next_safe_action"] == "Run completion-verifier.py from the packet directory."
    latest = snapshot["latest_run"]
    assert latest["runtime_kind"] == "hermes-profile"
    assert latest["hermes_profile"] == "hermes-qwen32-latest"
    assert latest["toolsets"] == ["file", "terminal"]
    assert latest["launch_status"] == "completed"
    assert latest["exit_code"] == 0
    assert latest["hermes_run"] == ".devflow/local-agent-runs/launched-hermes/hermes-run.json"
    assert latest["stdout_path"] == ".devflow/local-agent-runs/launched-hermes/hermes-stdout.txt"
    assert latest["stderr_path"] == ".devflow/local-agent-runs/launched-hermes/hermes-stderr.txt"
    assert latest["verification_status"] == "not_run"
    assert ".devflow/local-agent-runs/launched-hermes/hermes-run.json" in latest["evidence_paths"]
    assert ".devflow/local-agent-runs/launched-hermes/hermes-stdout.txt" in latest["evidence_paths"]
    assert ".devflow/local-agent-runs/launched-hermes/hermes-stderr.txt" in latest["evidence_paths"]
    assert not (result.run_dir / "verification-report.json").exists()


def test_serial_local_run_snapshot_projects_failed_hermes_launch(tmp_path: Path) -> None:
    setup_temp_git_repo(tmp_path)
    result = create_serial_local_agent_run(
        tmp_path,
        run_id="failed-hermes",
        phase="implementer",
        provider="ollama",
        model="qwen3.6-32b-256k:latest",
        allowed_files=["src/example.py"],
        verification_commands=["pytest tests/test_example.py -q"],
        runtime_kind="hermes-profile",
        hermes_profile="qwen-worker",
    )
    (result.run_dir / "hermes-stdout.txt").write_text("partial output\n", encoding="utf-8")
    (result.run_dir / "hermes-stderr.txt").write_text("launch failed\n", encoding="utf-8")
    (result.run_dir / "hermes-run.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "will_launch_hermes": True,
                "dry_run": False,
                "run_id": "failed-hermes",
                "hermes_profile": "hermes-qwen32-latest",
                "runtime_kind": "hermes-profile",
                "launch_status": "failed",
                "exit_code": 7,
                "stdout_path": ".devflow/local-agent-runs/failed-hermes/hermes-stdout.txt",
                "stderr_path": ".devflow/local-agent-runs/failed-hermes/hermes-stderr.txt",
                "hermes_run_path": ".devflow/local-agent-runs/failed-hermes/hermes-run.json",
                "verification_ran": False,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    snapshot = serial_local_agent_run_snapshot(tmp_path)

    assert snapshot["status"] == "failed"
    assert snapshot["run_state"] == "failed"
    assert snapshot["status_source"] == "hermes_run"
    assert snapshot["launch_status"] == "failed"
    assert snapshot["exit_code"] == 7
    assert snapshot["next_safe_action"] == (
        "Inspect Hermes launch stdout/stderr, repair the packet or runtime, then rerun Hermes manually."
    )


def test_serial_local_run_preflight_records_free_runtime(tmp_path: Path) -> None:
    setup_temp_git_repo(tmp_path)

    result = create_serial_local_agent_run(
        tmp_path,
        run_id="free-preflight",
        phase="implementer",
        provider="ollama",
        model="qwen3.6-32b-256k:latest",
        allowed_files=["src/example.py"],
        verification_commands=["pytest tests/test_example.py -q"],
    )

    preflight = result.manifest["preflight"]
    assert preflight["state"] == "free"
    assert preflight["launch_packet_ready"] is True
    assert preflight["owner"] is None
    assert preflight["lock_path"] == ".devflow/runtime/locks/local-model/global.lock"
    assert json.loads((result.run_dir / "preflight.json").read_text(encoding="utf-8")) == preflight


def test_serial_local_run_preflight_running_lock_blocks_launch_readiness(tmp_path: Path) -> None:
    setup_temp_git_repo(tmp_path)

    with local_model_runtime_lock(
        tmp_path,
        provider="ollama",
        model="qwen3.6-32b-256k:latest",
        task_id="task-0001",
        worker_id="qwen-worker",
        operation="serial-local-agent",
    ):
        result = create_serial_local_agent_run(
            tmp_path,
            run_id="running-preflight",
            phase="implementer",
            provider="ollama",
            model="qwen3.6-32b-256k:latest",
            allowed_files=["src/example.py"],
            verification_commands=["pytest tests/test_example.py -q"],
        )

    preflight = result.manifest["preflight"]
    assert preflight["state"] == "running"
    assert preflight["launch_packet_ready"] is False
    assert preflight["reason"] == "local model runtime is already running"
    assert preflight["owner"]["task_id"] == "task-0001"
    assert preflight["owner"]["worker_id"] == "qwen-worker"
    assert preflight["owner"]["operation"] == "serial-local-agent"
    assert preflight["owner"]["lock_path"] == preflight["lock_path"]


def test_serial_local_run_preflight_stale_lock_is_reported_not_removed(tmp_path: Path) -> None:
    setup_temp_git_repo(tmp_path)
    lock_dir = local_model_lock_dir(tmp_path, "ollama", "qwen3.6-32b-256k:latest")
    lock_dir.mkdir(parents=True)
    stale_owner = {
        "owner_id": "dead-owner",
        "provider": "ollama",
        "model": "qwen3.6-32b-256k:latest",
        "task_id": "task-dead",
        "worker_id": "qwen-worker",
        "operation": "serial-local-agent",
        "pid": 999_999_999,
        "host": "test-host",
        "acquired_at": "2026-06-21T00:00:00+00:00",
        "lock_path": ".devflow/runtime/locks/local-model/ollama/qwen3.6-32b-256k-latest.lock",
    }
    (lock_dir / "owner.json").write_text(json.dumps(stale_owner) + "\n", encoding="utf-8")

    result = create_serial_local_agent_run(
        tmp_path,
        run_id="stale-preflight",
        phase="implementer",
        provider="ollama",
        model="qwen3.6-32b-256k:latest",
        allowed_files=["src/example.py"],
        verification_commands=["pytest tests/test_example.py -q"],
    )

    preflight = result.manifest["preflight"]
    assert preflight["state"] == "stale"
    assert preflight["launch_packet_ready"] is False
    assert preflight["reason"] == "stale local model runtime lock requires explicit cleanup"
    assert preflight["owner"]["owner_id"] == "dead-owner"
    assert lock_dir.exists(), "packet preflight must report stale locks, not reclaim them"


def test_serial_local_run_preflight_ignores_different_provider_or_model_locks(tmp_path: Path) -> None:
    setup_temp_git_repo(tmp_path)

    with local_model_runtime_lock(
        tmp_path,
        provider="ollama",
        model="qwopus:latest",
        task_id="task-0002",
        worker_id="qwopus-worker",
    ):
        result = create_serial_local_agent_run(
            tmp_path,
            run_id="different-lock-preflight",
            phase="implementer",
            provider="ollama",
            model="qwen3.6-32b-256k:latest",
            allowed_files=["src/example.py"],
            verification_commands=["pytest tests/test_example.py -q"],
        )

    preflight = result.manifest["preflight"]
    assert preflight["state"] == "free"
    assert preflight["launch_packet_ready"] is True
    assert preflight["owner"] is None


def test_completion_verifier_passes_and_runs_only_provided_commands(tmp_path: Path) -> None:
    init_test_git_repo(tmp_path)
    src_file = tmp_path / "src/example.py"
    src_file.parent.mkdir()
    src_file.write_text("print('ok')\n", encoding="utf-8")
    marker = tmp_path / ".devflow/local-agent-runs/verifier-pass/command-marker.txt"
    command = _python_command(
        "from pathlib import Path; "
        "Path('.devflow/local-agent-runs/verifier-pass/command-marker.txt').write_text('ran', encoding='utf-8')"
    )
    result = create_serial_local_agent_run(
        tmp_path,
        run_id="verifier-pass",
        phase="verifier",
        provider="ollama",
        model="qwen3.6-32b-256k:latest",
        allowed_files=["src/example.py"],
        verification_commands=[command],
    )

    proc = _run_completion_verifier(result.run_dir)

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "SERIAL_PHASE_VERIFY=PASS" in proc.stdout
    assert marker.read_text(encoding="utf-8") == "ran"
    report = json.loads((result.run_dir / "verification-report.json").read_text(encoding="utf-8"))
    assert report["status"] == "PASS"
    assert report["failure_class"] is None
    assert [item["command"] for item in report["commands"]] == [command]
    assert report["off_allowlist_files"] == []


def test_completion_verifier_fails_off_allowlist_without_reclaiming_scope(tmp_path: Path) -> None:
    init_test_git_repo(tmp_path)
    (tmp_path / "src").mkdir()
    (tmp_path / "src/allowed.py").write_text("print('allowed')\n", encoding="utf-8")
    (tmp_path / "src/off.py").write_text("print('off')\n", encoding="utf-8")
    result = create_serial_local_agent_run(
        tmp_path,
        run_id="verifier-off-allowlist",
        phase="verifier",
        provider="ollama",
        model="qwen3.6-32b-256k:latest",
        allowed_files=["src/allowed.py"],
        verification_commands=[_python_command("raise SystemExit(0)")],
    )

    proc = _run_completion_verifier(result.run_dir)

    assert proc.returncode == 1
    assert "SERIAL_PHASE_VERIFY=FAIL" in proc.stdout
    assert "failure_class=off_allowlist" in proc.stdout
    report = json.loads((result.run_dir / "verification-report.json").read_text(encoding="utf-8"))
    assert report["failure_class"] == "off_allowlist"
    assert "src/off.py" in report["off_allowlist_files"]


def test_completion_verifier_fails_diff_hygiene(tmp_path: Path) -> None:
    init_test_git_repo(tmp_path)
    src_file = tmp_path / "src/example.py"
    src_file.parent.mkdir()
    src_file.write_text("print('bad')    \n", encoding="utf-8")
    result = create_serial_local_agent_run(
        tmp_path,
        run_id="verifier-diff-hygiene",
        phase="verifier",
        provider="ollama",
        model="qwen3.6-32b-256k:latest",
        allowed_files=["src/example.py"],
        verification_commands=[_python_command("raise SystemExit(0)")],
    )

    proc = _run_completion_verifier(result.run_dir)

    assert proc.returncode == 1
    assert "failure_class=diff_hygiene" in proc.stdout
    report = json.loads((result.run_dir / "verification-report.json").read_text(encoding="utf-8"))
    assert report["failure_class"] == "diff_hygiene"
    assert report["diff_hygiene_issues"][0]["path"] == "src/example.py"


def test_completion_verifier_diff_hygiene_detects_missing_final_newline(tmp_path: Path) -> None:
    init_test_git_repo(tmp_path)
    src_file = tmp_path / "src/example.py"
    src_file.parent.mkdir()
    src_file.write_text("print('missing newline')", encoding="utf-8")
    result = create_serial_local_agent_run(
        tmp_path,
        run_id="verifier-missing-newline",
        phase="verifier",
        provider="ollama",
        model="qwen3.6-32b-256k:latest",
        allowed_files=["src/example.py"],
        verification_commands=[_python_command("raise SystemExit(0)")],
    )

    proc = _run_completion_verifier(result.run_dir)

    assert proc.returncode == 1
    assert "failure_class=diff_hygiene" in proc.stdout
    report = json.loads((result.run_dir / "verification-report.json").read_text(encoding="utf-8"))
    assert report["failure_class"] == "diff_hygiene"
    assert {
        "path": "src/example.py",
        "line": None,
        "message": "missing final newline",
    } in report["diff_hygiene_issues"]


def test_completion_verifier_finds_repo_root_when_manifest_lacks_repo_root(tmp_path: Path) -> None:
    init_test_git_repo(tmp_path)
    src_file = tmp_path / "src/example.py"
    src_file.parent.mkdir()
    src_file.write_text("print('ok')\n", encoding="utf-8")
    result = create_serial_local_agent_run(
        tmp_path,
        run_id="verifier-root-fallback",
        phase="verifier",
        provider="ollama",
        model="qwen3.6-32b-256k:latest",
        allowed_files=["src/example.py"],
        verification_commands=[_python_command("raise SystemExit(0)")],
    )
    manifest_path = result.run_dir / "run.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["git"]["repo_root"] = ""
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    proc = _run_completion_verifier(result.run_dir)

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "SERIAL_PHASE_VERIFY=PASS" in proc.stdout
    report = json.loads((result.run_dir / "verification-report.json").read_text(encoding="utf-8"))
    assert report["repo_root"] == tmp_path.as_posix()


def test_completion_verifier_fails_test_failure(tmp_path: Path) -> None:
    init_test_git_repo(tmp_path)
    src_file = tmp_path / "src/example.py"
    src_file.parent.mkdir()
    src_file.write_text("print('ok')\n", encoding="utf-8")
    result = create_serial_local_agent_run(
        tmp_path,
        run_id="verifier-test-failure",
        phase="verifier",
        provider="ollama",
        model="qwen3.6-32b-256k:latest",
        allowed_files=["src/example.py"],
        verification_commands=[_python_command("raise SystemExit(3)")],
    )

    proc = _run_completion_verifier(result.run_dir)

    assert proc.returncode == 1
    assert "failure_class=test_failure" in proc.stdout
    report = json.loads((result.run_dir / "verification-report.json").read_text(encoding="utf-8"))
    assert report["failure_class"] == "test_failure"
    assert report["commands"][0]["returncode"] == 3


def test_completion_verifier_fails_missing_command(tmp_path: Path) -> None:
    init_test_git_repo(tmp_path)
    src_file = tmp_path / "src/example.py"
    src_file.parent.mkdir()
    src_file.write_text("print('ok')\n", encoding="utf-8")
    result = create_serial_local_agent_run(
        tmp_path,
        run_id="verifier-missing-command",
        phase="verifier",
        provider="ollama",
        model="qwen3.6-32b-256k:latest",
        allowed_files=["src/example.py"],
        verification_commands=["__definitely_missing_devflow_command__"],
    )

    proc = _run_completion_verifier(result.run_dir)

    assert proc.returncode == 1
    assert "failure_class=missing_command" in proc.stdout
    report = json.loads((result.run_dir / "verification-report.json").read_text(encoding="utf-8"))
    assert report["failure_class"] == "missing_command"
    assert report["commands"][0]["returncode"] == 127


@pytest.mark.parametrize(
    ("allowed_files", "verification_commands", "message"),
    [
        ([], ["pytest -q"], "allowed_files must contain at least one path"),
        (["src/example.py"], [], "verification_commands must contain at least one command"),
    ],
)
def test_serial_local_run_refuses_empty_required_lists(
    tmp_path: Path, allowed_files: list[str], verification_commands: list[str], message: str
) -> None:
    setup_temp_git_repo(tmp_path)

    with pytest.raises(SerialLocalAgentRunError, match=message):
        create_serial_local_agent_run(
            tmp_path,
            phase="implementer",
            provider="ollama",
            model="qwen3.6-32b-256k:latest",
            allowed_files=allowed_files,
            verification_commands=verification_commands,
        )


def test_serial_local_run_id_derivation_is_stable_and_path_safe(tmp_path: Path) -> None:
    first = derive_serial_local_run_id(
        phase="tiny_repair",
        provider="Ollama",
        model="qwen3.6-32b-256k:latest",
        allowed_files=["src/example.py"],
        verification_commands=["pytest tests/test_example.py -q"],
    )
    second = derive_serial_local_run_id(
        phase="tiny_repair",
        provider="Ollama",
        model="qwen3.6-32b-256k:latest",
        allowed_files=["src/example.py"],
        verification_commands=["pytest tests/test_example.py -q"],
    )

    assert first == second
    assert first.startswith("slr-tiny-repair-ollama-qwen3-6-32b-256k-latest-")
    assert serial_local_run_dir(tmp_path, "../Bad Run ID!") == (
        tmp_path / ".devflow" / "local-agent-runs" / "bad-run-id"
    )
