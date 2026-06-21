from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from devflow.control_room.hermes_worker_runtime import (
    HermesWorkerRuntimeError,
    dry_run_hermes_worker_runtime,
    run_hermes_worker_runtime,
)
from devflow.control_room.local_model_runtime_lock import (
    local_model_lock_dir,
    local_model_runtime_lock,
    local_model_runtime_status,
)
from devflow.control_room.serial_local_agent_run import create_serial_local_agent_run
from tests.helpers import setup_temp_git_repo


def _create_hermes_packet(tmp_path: Path, run_id: str = "hermes-runtime"):
    return create_serial_local_agent_run(
        tmp_path,
        run_id=run_id,
        phase="implementer",
        provider="ollama",
        model="qwen3.6-32b-256k:latest",
        allowed_files=["src/example.py"],
        verification_commands=["pytest tests/test_example.py -q"],
        runtime_kind="hermes-profile",
        hermes_profile="qwen-worker",
        toolsets=["file", "terminal"],
    )


def _fake_hermes_executable(tmp_path: Path, *, exit_code: int = 0) -> Path:
    fake = tmp_path / "fake-hermes"
    fake.write_text(
        "#!/usr/bin/env python3\n"
        "from __future__ import annotations\n"
        "import json\n"
        "import os\n"
        "import sys\n"
        "from pathlib import Path\n"
        "root = Path.cwd()\n"
        "lock_owner = root / '.devflow/runtime/locks/local-model/ollama/qwen3.6-32b-256k-latest.lock/owner.json'\n"
        "payload = {\n"
        "    'argv': sys.argv,\n"
        "    'cwd': os.getcwd(),\n"
        "    'lock_exists_during_launch': lock_owner.exists(),\n"
        "}\n"
        "(root / 'fake-hermes-argv.json').write_text(json.dumps(payload, sort_keys=True) + '\\n', encoding='utf-8')\n"
        "print('fake hermes stdout')\n"
        "print('fake hermes stderr', file=sys.stderr)\n"
        f"raise SystemExit({exit_code})\n",
        encoding="utf-8",
    )
    fake.chmod(fake.stat().st_mode | 0o111)
    return fake


def test_dry_run_previews_argv_without_invoking_hermes(tmp_path: Path) -> None:
    setup_temp_git_repo(tmp_path)
    result = _create_hermes_packet(tmp_path)

    with patch("subprocess.run", side_effect=AssertionError("dry-run must not invoke subprocess.run")), patch(
        "subprocess.Popen", side_effect=AssertionError("dry-run must not invoke subprocess.Popen")
    ):
        payload = dry_run_hermes_worker_runtime(
            tmp_path,
            run_id="hermes-runtime",
            hermes_profile="qwen-worker",
        )

    assert payload["will_launch_hermes"] is False
    assert payload["launch_allowed"] is True
    assert payload["run_id"] == "hermes-runtime"
    assert payload["hermes_profile"] == "qwen-worker"
    assert payload["runtime_kind"] == "hermes-profile"
    assert payload["preflight_state"] == "free"
    assert payload["packet_path"] == ".devflow/local-agent-runs/hermes-runtime/worker-packet.md"
    assert payload["run_manifest_path"] == ".devflow/local-agent-runs/hermes-runtime/run.json"
    assert payload["command_preview"][:5] == ["hermes", "-p", "qwen-worker", "chat", "-q"]
    assert all(isinstance(part, str) for part in payload["command_preview"])
    assert "worker-packet.md" in payload["command_preview"][5]
    assert not (result.run_dir / "hermes-run.json").exists()


def test_dry_run_refuses_missing_run_and_missing_worker_packet(tmp_path: Path) -> None:
    setup_temp_git_repo(tmp_path)

    with pytest.raises(HermesWorkerRuntimeError, match="serial local-agent run 'missing' was not found"):
        dry_run_hermes_worker_runtime(tmp_path, run_id="missing", hermes_profile="qwen-worker")

    result = _create_hermes_packet(tmp_path, run_id="missing-packet")
    (result.run_dir / "worker-packet.md").unlink()

    with pytest.raises(HermesWorkerRuntimeError, match="worker-packet.md is missing"):
        dry_run_hermes_worker_runtime(tmp_path, run_id="missing-packet", hermes_profile="qwen-worker")


def test_dry_run_refuses_running_same_model_lock(tmp_path: Path) -> None:
    setup_temp_git_repo(tmp_path)
    _create_hermes_packet(tmp_path, run_id="running-lock")

    with local_model_runtime_lock(
        tmp_path,
        provider="ollama",
        model="qwen3.6-32b-256k:latest",
        task_id="task-0001",
        worker_id="qwen-worker",
        operation="hermes-worker-runtime",
    ):
        with pytest.raises(HermesWorkerRuntimeError, match="local model runtime is already running"):
            dry_run_hermes_worker_runtime(tmp_path, run_id="running-lock", hermes_profile="qwen-worker")


def test_dry_run_refuses_stale_same_model_lock(tmp_path: Path) -> None:
    setup_temp_git_repo(tmp_path)
    _create_hermes_packet(tmp_path, run_id="stale-lock")
    lock_dir = local_model_lock_dir(tmp_path, "ollama", "qwen3.6-32b-256k:latest")
    lock_dir.mkdir(parents=True)
    (lock_dir / "owner.json").write_text(
        json.dumps(
            {
                "owner_id": "dead-owner",
                "provider": "ollama",
                "model": "qwen3.6-32b-256k:latest",
                "task_id": "task-dead",
                "worker_id": "qwen-worker",
                "operation": "hermes-worker-runtime",
                "pid": 999_999_999,
                "host": "test-host",
                "acquired_at": "2026-06-21T00:00:00+00:00",
                "lock_path": ".devflow/runtime/locks/local-model/ollama/qwen3.6-32b-256k-latest.lock",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(HermesWorkerRuntimeError, match="stale local model runtime lock requires explicit cleanup"):
        dry_run_hermes_worker_runtime(tmp_path, run_id="stale-lock", hermes_profile="qwen-worker")


def test_dry_run_refuses_manual_runtime_unless_forced(tmp_path: Path) -> None:
    setup_temp_git_repo(tmp_path)
    create_serial_local_agent_run(
        tmp_path,
        run_id="manual-runtime",
        phase="implementer",
        provider="ollama",
        model="qwen3.6-32b-256k:latest",
        allowed_files=["src/example.py"],
        verification_commands=["pytest tests/test_example.py -q"],
    )

    with pytest.raises(HermesWorkerRuntimeError, match="runtime 'manual'.*--force"):
        dry_run_hermes_worker_runtime(tmp_path, run_id="manual-runtime", hermes_profile="qwen-worker")

    payload = dry_run_hermes_worker_runtime(
        tmp_path,
        run_id="manual-runtime",
        hermes_profile="qwen-worker",
        force=True,
    )

    assert payload["will_launch_hermes"] is False
    assert payload["launch_allowed"] is True
    assert payload["runtime_kind"] == "manual"
    assert payload["force"] is True


def test_dry_run_refuses_profile_mismatch(tmp_path: Path) -> None:
    setup_temp_git_repo(tmp_path)
    _create_hermes_packet(tmp_path, run_id="profile-mismatch")

    with pytest.raises(HermesWorkerRuntimeError, match="does not match packet Hermes profile"):
        dry_run_hermes_worker_runtime(tmp_path, run_id="profile-mismatch", hermes_profile="other-profile")


def test_real_launch_fake_hermes_captures_evidence_and_releases_lock(tmp_path: Path) -> None:
    setup_temp_git_repo(tmp_path)
    result = _create_hermes_packet(tmp_path, run_id="real-launch")
    fake = _fake_hermes_executable(tmp_path)

    payload = run_hermes_worker_runtime(
        tmp_path,
        run_id="real-launch",
        hermes_profile="qwen-worker",
        hermes_executable=fake.as_posix(),
        timeout_seconds=10,
    )

    assert payload["will_launch_hermes"] is True
    assert payload["launch_status"] == "completed"
    assert payload["exit_code"] == 0
    assert payload["verification_ran"] is False
    assert payload["next_safe_action"] == "Run completion-verifier.py from the packet directory."
    assert payload["stdout_path"] == ".devflow/local-agent-runs/real-launch/hermes-stdout.txt"
    assert payload["stderr_path"] == ".devflow/local-agent-runs/real-launch/hermes-stderr.txt"
    assert (result.run_dir / "hermes-stdout.txt").read_text(encoding="utf-8") == "fake hermes stdout\n"
    assert (result.run_dir / "hermes-stderr.txt").read_text(encoding="utf-8") == "fake hermes stderr\n"
    assert not (result.run_dir / "verification-report.json").exists()

    evidence = json.loads((result.run_dir / "hermes-run.json").read_text(encoding="utf-8"))
    assert evidence["launch_status"] == "completed"
    assert evidence["exit_code"] == 0
    assert evidence["command_preview"] == payload["command_preview"]
    assert evidence["verification_ran"] is False

    fake_payload = json.loads((tmp_path / "fake-hermes-argv.json").read_text(encoding="utf-8"))
    assert fake_payload["argv"][1:5] == ["-p", "qwen-worker", "chat", "-q"]
    assert "worker-packet.md" in fake_payload["argv"][5]
    assert fake_payload["cwd"] == tmp_path.as_posix()
    assert fake_payload["lock_exists_during_launch"] is True
    assert local_model_runtime_status(tmp_path, provider="ollama", model="qwen3.6-32b-256k:latest") is None


def test_real_launch_nonzero_writes_failed_evidence(tmp_path: Path) -> None:
    setup_temp_git_repo(tmp_path)
    result = _create_hermes_packet(tmp_path, run_id="failed-launch")
    fake = _fake_hermes_executable(tmp_path, exit_code=7)

    payload = run_hermes_worker_runtime(
        tmp_path,
        run_id="failed-launch",
        hermes_profile="qwen-worker",
        hermes_executable=fake.as_posix(),
        timeout_seconds=10,
    )

    assert payload["will_launch_hermes"] is True
    assert payload["launch_status"] == "failed"
    assert payload["exit_code"] == 7
    assert (result.run_dir / "hermes-stdout.txt").read_text(encoding="utf-8") == "fake hermes stdout\n"
    assert (result.run_dir / "hermes-stderr.txt").read_text(encoding="utf-8") == "fake hermes stderr\n"
    evidence = json.loads((result.run_dir / "hermes-run.json").read_text(encoding="utf-8"))
    assert evidence["launch_status"] == "failed"
    assert evidence["exit_code"] == 7
    assert evidence["verification_ran"] is False
    assert local_model_runtime_status(tmp_path, provider="ollama", model="qwen3.6-32b-256k:latest") is None


def test_real_launch_refuses_existing_runtime_lock(tmp_path: Path) -> None:
    setup_temp_git_repo(tmp_path)
    _create_hermes_packet(tmp_path, run_id="locked-launch")
    fake = _fake_hermes_executable(tmp_path)

    with local_model_runtime_lock(
        tmp_path,
        provider="ollama",
        model="qwen3.6-32b-256k:latest",
        task_id="task-locked",
        worker_id="qwen-worker",
        operation="already-running",
    ):
        with pytest.raises(HermesWorkerRuntimeError, match="local model runtime is already running"):
            run_hermes_worker_runtime(
                tmp_path,
                run_id="locked-launch",
                hermes_profile="qwen-worker",
                hermes_executable=fake.as_posix(),
                timeout_seconds=10,
            )

    assert not (tmp_path / "fake-hermes-argv.json").exists()


def test_real_launch_missing_executable_writes_failed_evidence(tmp_path: Path) -> None:
    setup_temp_git_repo(tmp_path)
    result = _create_hermes_packet(tmp_path, run_id="missing-executable")

    payload = run_hermes_worker_runtime(
        tmp_path,
        run_id="missing-executable",
        hermes_profile="qwen-worker",
        hermes_executable=(tmp_path / "does-not-exist-hermes").as_posix(),
        timeout_seconds=10,
    )

    assert payload["launch_status"] == "failed"
    assert payload["exit_code"] == 127
    assert "does-not-exist-hermes" in (result.run_dir / "hermes-stderr.txt").read_text(encoding="utf-8")
    evidence = json.loads((result.run_dir / "hermes-run.json").read_text(encoding="utf-8"))
    assert evidence["exit_code"] == 127
    assert evidence["verification_ran"] is False
    assert local_model_runtime_status(tmp_path, provider="ollama", model="qwen3.6-32b-256k:latest") is None


def test_real_launch_timeout_writes_timeout_evidence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    setup_temp_git_repo(tmp_path)
    result = _create_hermes_packet(tmp_path, run_id="timeout-launch")
    fake = _fake_hermes_executable(tmp_path)

    def raise_timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], kwargs.get("timeout") or 1, output="partial out", stderr="partial err")

    monkeypatch.setattr("subprocess.run", raise_timeout)

    payload = run_hermes_worker_runtime(
        tmp_path,
        run_id="timeout-launch",
        hermes_profile="qwen-worker",
        hermes_executable=fake.as_posix(),
        timeout_seconds=3,
    )

    assert payload["launch_status"] == "timeout"
    assert payload["exit_code"] == 124
    assert (result.run_dir / "hermes-stdout.txt").read_text(encoding="utf-8") == "partial out"
    assert (result.run_dir / "hermes-stderr.txt").read_text(encoding="utf-8") == "partial err"
    evidence = json.loads((result.run_dir / "hermes-run.json").read_text(encoding="utf-8"))
    assert evidence["launch_status"] == "timeout"
    assert evidence["verification_ran"] is False
    assert local_model_runtime_status(tmp_path, provider="ollama", model="qwen3.6-32b-256k:latest") is None


def test_dry_run_refuses_invalid_or_incomplete_manifest(tmp_path: Path) -> None:
    setup_temp_git_repo(tmp_path)
    result = _create_hermes_packet(tmp_path, run_id="bad-manifest")
    manifest_path = result.run_dir / "run.json"
    manifest_path.write_text("{not json\n", encoding="utf-8")

    with pytest.raises(HermesWorkerRuntimeError, match="not valid JSON"):
        dry_run_hermes_worker_runtime(tmp_path, run_id="bad-manifest", hermes_profile="qwen-worker")

    result = _create_hermes_packet(tmp_path, run_id="missing-provider")
    manifest = json.loads((result.run_dir / "run.json").read_text(encoding="utf-8"))
    manifest.pop("provider")
    (result.run_dir / "run.json").write_text(json.dumps(manifest) + "\n", encoding="utf-8")

    with pytest.raises(HermesWorkerRuntimeError, match="provider is required"):
        dry_run_hermes_worker_runtime(tmp_path, run_id="missing-provider", hermes_profile="qwen-worker")
