from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from typer.testing import CliRunner

from devflow.cli import app
from devflow.control_room import local_model_readiness as readiness
from tests.helpers import setup_temp_git_repo


runner = CliRunner()


def _planner_payload(*, provision_commands: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    commands = provision_commands if provision_commands is not None else [
        {
            "kind": "provider",
            "lane_id": "missing_local",
            "provider_id": "local-gateway",
            "profile_id": "local-gateway-model",
            "supported": True,
            "command": "devflow agent add-provider local-gateway --adapter openai_compatible --base-url http://127.0.0.1:9999/v1 --json",
            "argv": [
                "devflow",
                "agent",
                "add-provider",
                "local-gateway",
                "--adapter",
                "openai_compatible",
                "--base-url",
                "http://127.0.0.1:9999/v1",
                "--json",
            ],
            "reason": "Register provider 'local-gateway' for lane 'missing_local'.",
        }
    ]
    return {
        "schema_version": 1,
        "manifest_schema_version": 1,
        "manifest_path": "test-manifest.yaml",
        "machine": {"total_memory_gb": 16, "machine_class": "mac_mini"},
        "inventory_summary": {},
        "lanes": [
            {
                "lane_id": "ready_local",
                "readiness": "ready",
                "ready": True,
                "ram_status": "ideal",
                "provider_registered": True,
                "profile_registered": True,
                "provider_missing_env": False,
                "inventory_status": "available",
                "provision_commands": [],
                "start_commands": [],
            },
            {
                "lane_id": "missing_local",
                "readiness": "needs_provider",
                "ready": False,
                "ram_status": "ideal",
                "provider_registered": False,
                "profile_registered": False,
                "provider_missing_env": False,
                "inventory_status": None,
                "provision_commands": commands,
                "start_commands": [
                    {
                        "kind": "start",
                        "lane_id": "missing_local",
                        "provider_id": "local-gateway",
                        "profile_id": "local-gateway-model",
                        "supported": True,
                        "command": "devflow local-model start hermes-qwen32 --replace --json",
                        "argv": ["devflow", "local-model", "start", "hermes-qwen32", "--replace", "--json"],
                        "reason": "Start managed local model server for lane 'missing_local'.",
                    }
                ],
            },
        ],
        "provision_commands": commands,
        "start_commands": [
            {
                "kind": "start",
                "lane_id": "missing_local",
                "provider_id": "local-gateway",
                "profile_id": "local-gateway-model",
                "supported": True,
                "command": "devflow local-model start hermes-qwen32 --replace --json",
                "argv": ["devflow", "local-model", "start", "hermes-qwen32", "--replace", "--json"],
                "reason": "Start managed local model server for lane 'missing_local'.",
            }
        ],
        "summary": {
            "lane_count": 2,
            "ready_count": 1,
            "blocked_count": 0,
            "needs_action_count": 1,
            "start_command_count": 1,
        },
    }


def test_doctor_provision_dry_run_prints_readiness_and_exact_commands(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(readiness, "build_local_model_readiness_plan", lambda root: _planner_payload())

    result = runner.invoke(app, ["doctor", "--provision"])

    assert result.exit_code == 0, result.output
    assert "Local model readiness (dry run)" in result.output
    assert "readiness: 1/2 lanes ready; 0 blocked; 1 need onboarding" in result.output
    assert "missing_local: needs_provider" in result.output
    assert "devflow agent add-provider local-gateway --adapter openai_compatible" in result.output
    assert "devflow local-model start hermes-qwen32 --replace --json" in result.output
    assert not (tmp_path / ".devflow" / "local-model-readiness").exists()


def test_doctor_provision_json_exposes_payload_without_mutating_state(
    tmp_path: Path,
    monkeypatch,
) -> None:
    plan = _planner_payload()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(readiness, "build_local_model_readiness_plan", lambda root: plan)

    result = runner.invoke(app, ["doctor", "--provision", "--json"])

    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == plan
    assert not (tmp_path / ".devflow").exists()


def test_doctor_provision_apply_runs_supported_commands_and_records_evidence(
    tmp_path: Path,
    monkeypatch,
) -> None:
    commands = [
        _planner_payload()["provision_commands"][0],
        {
            "kind": "model",
            "lane_id": "missing_local",
            "provider_id": "local-gateway",
            "profile_id": "local-gateway-model",
            "supported": True,
            "command": "devflow agent add-model --provider local-gateway --model local-model --authority advisory --role local_senior_worker --profile-id local-gateway-model --json",
            "argv": [
                "devflow",
                "agent",
                "add-model",
                "--provider",
                "local-gateway",
                "--model",
                "local-model",
                "--authority",
                "advisory",
                "--role",
                "local_senior_worker",
                "--profile-id",
                "local-gateway-model",
                "--json",
            ],
            "reason": "Register model profile 'local-gateway-model' for lane 'missing_local'.",
        },
    ]
    calls: list[list[str]] = []

    def fake_run(args: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, stdout='{"status":"written"}', stderr="")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(readiness, "build_local_model_readiness_plan", lambda root: _planner_payload(provision_commands=commands))
    monkeypatch.setattr(readiness.subprocess, "run", fake_run)

    result = runner.invoke(app, ["doctor", "--provision", "--apply"])

    assert result.exit_code == 0, result.output
    assert "status: applied" in result.output
    assert len(calls) == 3
    assert calls[0][:3] == [sys.executable, "-m", "devflow.cli"]
    assert calls[0][3:6] == ["agent", "add-provider", "local-gateway"]
    assert calls[1][:5] == [sys.executable, "-m", "devflow.cli", "agent", "add-model"]
    assert calls[2] == [
        sys.executable,
        "-m",
        "devflow.cli",
        "local-model",
        "start",
        "hermes-qwen32",
        "--replace",
        "--json",
    ]

    evidence_files = sorted((tmp_path / ".devflow" / "local-model-readiness").glob("run-*/command-*.json"))
    assert len(evidence_files) == 3
    first_evidence = json.loads(evidence_files[0].read_text(encoding="utf-8"))
    assert first_evidence["status"] == "succeeded"
    assert first_evidence["executed_argv"] == calls[0]
    assert first_evidence["stdout"] == '{"status":"written"}'
    latest = json.loads((tmp_path / ".devflow" / "local-model-readiness" / "latest.json").read_text(encoding="utf-8"))
    assert latest["status"] == "applied"
    assert latest["applied_count"] == 3
    assert latest["provision_command_count"] == 2
    assert latest["start_command_count"] == 1


def test_doctor_provision_apply_blocks_non_onboarding_commands(
    tmp_path: Path,
    monkeypatch,
) -> None:
    unsafe = [
        {
            "kind": "promote",
            "lane_id": "missing_local",
            "provider_id": "local-gateway",
            "profile_id": "local-gateway-model",
            "supported": True,
            "command": "devflow task promote task-0001",
            "argv": ["devflow", "task", "promote", "task-0001"],
            "reason": "Unsafe command should never run.",
        }
    ]

    def fake_run(args: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        raise AssertionError(f"unsafe command was run: {args}")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(readiness, "build_local_model_readiness_plan", lambda root: _planner_payload(provision_commands=unsafe))
    monkeypatch.setattr(readiness.subprocess, "run", fake_run)

    result = runner.invoke(app, ["doctor", "--provision", "--apply"])

    assert result.exit_code == 1, result.output
    assert "status: failed" in result.output
    assert "Refusing non-onboarding command" in result.output
    evidence_files = sorted((tmp_path / ".devflow" / "local-model-readiness").glob("run-*/command-*.json"))
    assert len(evidence_files) == 1
    evidence = json.loads(evidence_files[0].read_text(encoding="utf-8"))
    assert evidence["status"] == "blocked"
    assert "Refusing non-onboarding command" in evidence["reason"]


def test_doctor_provision_apply_blocks_unmanaged_start_command_shape(
    tmp_path: Path,
    monkeypatch,
) -> None:
    plan = _planner_payload(provision_commands=[])
    plan["start_commands"] = [
        {
            "kind": "start",
            "lane_id": "missing_local",
            "provider_id": "local-gateway",
            "profile_id": "local-gateway-model",
            "supported": True,
            "command": "devflow local-model start hermes-qwen32 --binary custom-llama --json",
            "argv": ["devflow", "local-model", "start", "hermes-qwen32", "--binary", "custom-llama", "--json"],
            "reason": "Unsafe command shape should never run.",
        }
    ]

    def fake_run(args: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        raise AssertionError(f"unsafe start command was run: {args}")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(readiness, "build_local_model_readiness_plan", lambda root: plan)
    monkeypatch.setattr(readiness.subprocess, "run", fake_run)

    result = runner.invoke(app, ["doctor", "--provision", "--apply"])

    assert result.exit_code == 1, result.output
    assert "status: failed" in result.output
    evidence_files = sorted((tmp_path / ".devflow" / "local-model-readiness").glob("run-*/command-*.json"))
    assert len(evidence_files) == 1
    evidence = json.loads(evidence_files[0].read_text(encoding="utf-8"))
    assert evidence["status"] == "blocked"
    assert "managed 'devflow local-model start <profile> --replace --json' shape" in evidence["reason"]


def test_status_json_contains_local_model_inventory_and_readiness(
    tmp_path: Path,
    monkeypatch,
) -> None:
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", tmp_path.as_posix())
    monkeypatch.setenv("DEVFLOW_MACHINE_RAM_GB", "16")

    result = runner.invoke(app, ["status", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["local_model_inventory"]["schema_version"] == 1
    assert payload["local_model_readiness"]["schema_version"] == 1
    assert payload["local_model_readiness"]["summary"]["lane_count"] >= 1
    assert isinstance(payload["local_model_readiness"]["provision_commands"], list)
