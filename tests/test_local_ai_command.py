from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from typer.testing import CliRunner

from devflow.cli import app
from devflow.control_room.models import TaskRecord
from devflow.control_room.persistence import save_task
from devflow.control_room.local_model_readiness import (
    ExpectedLocalModelLane,
    LocalModelExpectedProfilesManifest,
)
from devflow.control_room.task_packet import build_task_packet


runner = CliRunner()


class _MockResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._body = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> "_MockResponse":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


def _write_task_and_packet(
    root: Path,
    task_id: str,
    title: str,
) -> tuple[Path, TaskRecord]:
    task_dir = root / ".devflow" / "tasks" / task_id
    now = datetime.now(timezone.utc)
    task = TaskRecord(
        id=task_id,
        title=title,
        created_at=now,
        updated_at=now,
        workspace=".",
        status="created",
    )
    save_task(task_dir, task)

    task_packet = build_task_packet(task_id, root=root)
    packet_path = root / f"{task_id}-packet.json"
    packet_path.write_text(
        task_packet.model_dump_json(indent=2),
        encoding="utf-8",
    )
    return packet_path, task


def _manifest() -> LocalModelExpectedProfilesManifest:
    lanes = {
        "hermes-qwen32-latest": ExpectedLocalModelLane(
            lane_id="hermes-qwen32-latest",
            profile_id="hermes-qwen32-latest",
            provider_id="ollama",
            model_id="qwen32:latest",
            adapter="ollama_chat",
            role="frontier_planner_architect_reviewer",
            authority="advisory",
            min_ram_gb=12,
            ideal_ram_gb=16,
            weight_class="medium",
            quant_policy="provider-managed",
            base_url="http://127.0.0.1:11434",
            port=11434,
            local_server_backed=False,
            fallback_lanes=(),
        ),
        "hermes-gemma12b-latest": ExpectedLocalModelLane(
            lane_id="hermes-gemma12b-latest",
            profile_id="hermes-gemma12b-latest",
            provider_id="ollama",
            model_id="gemma12b:latest",
            adapter="ollama_chat",
            role="local_senior_worker",
            authority="read-only",
            min_ram_gb=24,
            ideal_ram_gb=48,
            weight_class="medium",
            quant_policy="qat",
            base_url="http://127.0.0.1:11434",
            port=11434,
            local_server_backed=False,
            fallback_lanes=(),
        ),
        "hermes-qwopus-35b": ExpectedLocalModelLane(
            lane_id="hermes-qwopus-35b",
            profile_id="hermes-qwopus-35b",
            provider_id="ollama",
            model_id="qwopus-35b",
            adapter="ollama_chat",
            role="implementation_worker",
            authority="read-only",
            min_ram_gb=32,
            ideal_ram_gb=64,
            weight_class="heavy",
            quant_policy="provider-managed",
            base_url="http://127.0.0.1:11434",
            port=11434,
            local_server_backed=False,
            fallback_lanes=(),
        ),
        "hermes-qwen36-27b-q5-mtp": ExpectedLocalModelLane(
            lane_id="hermes-qwen36-27b-q5-mtp",
            profile_id="hermes-qwen36-27b-q5-mtp",
            provider_id="qwen36-27b-q5-mtp",
            model_id="qwen36-27b-q5-mtp",
            adapter="openai_compatible",
            role="frontier_planner_architect_reviewer",
            authority="advisory",
            min_ram_gb=32,
            ideal_ram_gb=64,
            weight_class="heavy",
            quant_policy="q5-k-m",
            base_url="http://127.0.0.1:8083/v1",
            port=8083,
            local_server_backed=True,
            fallback_lanes=(),
        ),
        "hermes-gemma4-e4b": ExpectedLocalModelLane(
            lane_id="hermes-gemma4-e4b",
            profile_id="hermes-gemma4-e4b",
            provider_id="ollama",
            model_id="gemma4-e4b:latest",
            adapter="ollama_chat",
            role="scout",
            authority="read-only",
            min_ram_gb=0,
            ideal_ram_gb=0,
            weight_class="medium",
            quant_policy="provider-managed",
            base_url="http://127.0.0.1:11434",
            port=11434,
            local_server_backed=False,
            fallback_lanes=(),
        ),
        "hermes-ornith-9b": ExpectedLocalModelLane(
            lane_id="hermes-ornith-9b",
            profile_id="hermes-ornith-9b",
            provider_id="ornith-9b",
            model_id="ornith-9b",
            adapter="openai_compatible",
            role="frontier_planner_architect_reviewer",
            authority="advisory",
            min_ram_gb=24,
            ideal_ram_gb=48,
            weight_class="medium",
            quant_policy="q4-k-m",
            base_url="http://127.0.0.1:8085/v1",
            port=8085,
            local_server_backed=True,
            fallback_lanes=(),
        ),
        "hermes-ornith-35b": ExpectedLocalModelLane(
            lane_id="hermes-ornith-35b",
            profile_id="hermes-ornith-35b",
            provider_id="ornith-35b",
            model_id="ornith-35b",
            adapter="openai_compatible",
            role="frontier_planner_architect_reviewer",
            authority="advisory",
            min_ram_gb=64,
            ideal_ram_gb=96,
            weight_class="heavy",
            quant_policy="q4-k-m",
            base_url="http://127.0.0.1:8084/v1",
            port=8084,
            local_server_backed=True,
            fallback_lanes=(),
        ),
        "hermes-minimaxm3": ExpectedLocalModelLane(
            lane_id="hermes-minimaxm3",
            profile_id="hermes-minimaxm3",
            provider_id="openrouter",
            model_id="minimax/minimax-m3",
            adapter="openai_compatible",
            role="frontier_planner_architect_reviewer",
            authority="advisory",
            min_ram_gb=0,
            ideal_ram_gb=0,
            weight_class="remote",
            quant_policy="provider-managed",
            base_url="https://openrouter.ai/api/v1",
            local_server_backed=False,
            api_key_env="OPENROUTER_API_KEY",
            fallback_lanes=(),
        ),
        "hermes-qwen37plus": ExpectedLocalModelLane(
            lane_id="hermes-qwen37plus",
            profile_id="hermes-qwen37plus",
            provider_id="openrouter",
            model_id="qwen/qwen3.7-plus",
            adapter="openai_compatible",
            role="frontier_planner_architect_reviewer",
            authority="advisory",
            min_ram_gb=0,
            ideal_ram_gb=0,
            weight_class="remote",
            quant_policy="provider-managed",
            base_url="https://openrouter.ai/api/v1",
            local_server_backed=False,
            api_key_env="OPENROUTER_API_KEY",
            fallback_lanes=(),
        ),
        "hermes-sonnet46": ExpectedLocalModelLane(
            lane_id="hermes-sonnet46",
            profile_id="hermes-sonnet46",
            provider_id="openrouter",
            model_id="anthropic/claude-sonnet-4.6",
            adapter="openai_compatible",
            role="frontier_planner_architect_reviewer",
            authority="advisory",
            min_ram_gb=0,
            ideal_ram_gb=0,
            weight_class="remote",
            quant_policy="provider-managed",
            base_url="https://openrouter.ai/api/v1",
            local_server_backed=False,
            api_key_env="OPENROUTER_API_KEY",
            fallback_lanes=(),
        ),
        "hermes-opus48": ExpectedLocalModelLane(
            lane_id="hermes-opus48",
            profile_id="hermes-opus48",
            provider_id="openrouter",
            model_id="anthropic/claude-opus-4.8",
            adapter="openai_compatible",
            role="frontier_planner_architect_reviewer",
            authority="advisory",
            min_ram_gb=0,
            ideal_ram_gb=0,
            weight_class="remote",
            quant_policy="provider-managed",
            base_url="https://openrouter.ai/api/v1",
            local_server_backed=False,
            api_key_env="OPENROUTER_API_KEY",
            fallback_lanes=(),
        ),
        "hermes-codex-gpt55": ExpectedLocalModelLane(
            lane_id="hermes-codex-gpt55",
            profile_id="hermes-codex-gpt55",
            provider_id="openai-codex",
            model_id="gpt-5.5",
            adapter="hermes_profile",
            role="frontier_planner_architect_reviewer",
            authority="advisory",
            min_ram_gb=0,
            ideal_ram_gb=0,
            weight_class="remote",
            quant_policy="subscription-managed",
            base_url="https://chatgpt.com/backend-api/codex",
            local_server_backed=False,
            fallback_lanes=(),
        ),
    }
    return LocalModelExpectedProfilesManifest(schema_version=1, lanes=lanes, source_path=Path("test-manifest.yaml"))


def _write_latest_capacity_report(
    root: Path,
    *,
    status: str = "success",
    max_safe_concurrency: int = 1,
) -> None:
    payload = {
        "schema_version": 1,
        "status": status,
        "max_safe_concurrency": max_safe_concurrency,
    }
    report_dir = root / ".devflow" / "local-ai" / "scout-capacity"
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "latest.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")


def test_local_ai_snapshot_json_reports_targets_warning_and_start_recommendation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from devflow.control_room import local_ai_fleet

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(local_ai_fleet, "load_expected_local_model_manifest", _manifest)
    monkeypatch.setattr(local_ai_fleet.local_model_server, "local_model_server_status", lambda include_ollama=True: {"status": "idle", "running_count": 0, "processes": []})
    monkeypatch.setattr(local_ai_fleet.local_model_server, "build_local_model_server_inventory", lambda include_ollama=True: {"action": "inventory", "profiles": []})
    monkeypatch.setattr(local_ai_fleet, "inspect_ollama_loaded_models", lambda: {"status": "idle", "loaded_models": []})
    monkeypatch.setattr(local_ai_fleet, "list_local_model_runtime_status", lambda root: {})

    result = runner.invoke(app, ["local-ai", "snapshot", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["policy"]["one_active_model_role"] is True
    assert payload["supervisor_target"]["server_id"] == "qwen36-27b-q5-mtp"
    assert payload["scout_target"]["label"] == "hermes-gemma4-e4b"
    assert payload["scout_target"]["model_id"] == "gemma4-e4b:latest"
    assert payload["warnings"] == []
    assert payload["active_model_processes"] == []
    assert payload["recommended_next_action"]["recommended_command"] == "devflow local-model start qwen36-27b-q5-mtp --dry-run --json"


def test_local_ai_recommend_json_prefers_stop_all_when_process_running(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from devflow.control_room import local_ai_fleet

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(local_ai_fleet, "load_expected_local_model_manifest", _manifest)
    monkeypatch.setattr(
        local_ai_fleet.local_model_server,
        "local_model_server_status",
        lambda include_ollama=True: {
            "status": "running",
            "running_count": 1,
            "processes": [{"pid": 42, "kind": "llama-server", "provider": "ornith-9b", "model": "ornith-9b"}],
        },
    )
    monkeypatch.setattr(local_ai_fleet.local_model_server, "build_local_model_server_inventory", lambda include_ollama=True: {"action": "inventory", "profiles": []})
    monkeypatch.setattr(local_ai_fleet, "inspect_ollama_loaded_models", lambda: {"status": "idle", "loaded_models": []})
    monkeypatch.setattr(local_ai_fleet, "list_local_model_runtime_status", lambda root: {})

    result = runner.invoke(app, ["local-ai", "recommend", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["action_id"] == "stop_before_switch"
    assert payload["recommended_command"] == "devflow local-ai stop-all --dry-run --json"
    assert payload["fallback_command"] == "devflow local-model stop --dry-run --json"


def test_local_ai_recommend_ignores_idle_ollama_daemon(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from devflow.control_room import local_ai_fleet

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(local_ai_fleet, "load_expected_local_model_manifest", _manifest)
    monkeypatch.setattr(
        local_ai_fleet.local_model_server,
        "local_model_server_status",
        lambda include_ollama=True: {
            "status": "running",
            "running_count": 1,
            "processes": [{"pid": 42, "kind": "ollama", "provider": "local", "model": None}],
        },
    )
    monkeypatch.setattr(local_ai_fleet.local_model_server, "build_local_model_server_inventory", lambda include_ollama=True: {"action": "inventory", "profiles": []})
    monkeypatch.setattr(local_ai_fleet, "inspect_ollama_loaded_models", lambda: {"status": "idle", "loaded_models": []})
    monkeypatch.setattr(local_ai_fleet, "list_local_model_runtime_status", lambda root: {})

    result = runner.invoke(app, ["local-ai", "recommend", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["action_id"] == "start_supervisor_dry_run"
    assert payload["recommended_command"] == "devflow local-model start qwen36-27b-q5-mtp --dry-run --json"


def test_local_ai_recommend_stops_when_ollama_model_is_loaded(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from devflow.control_room import local_ai_fleet

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(local_ai_fleet, "load_expected_local_model_manifest", _manifest)
    monkeypatch.setattr(
        local_ai_fleet.local_model_server,
        "local_model_server_status",
        lambda include_ollama=True: {
            "status": "running",
            "running_count": 1,
            "processes": [{"pid": 42, "kind": "ollama", "provider": "local", "model": None}],
        },
    )
    monkeypatch.setattr(local_ai_fleet.local_model_server, "build_local_model_server_inventory", lambda include_ollama=True: {"action": "inventory", "profiles": []})
    monkeypatch.setattr(
        local_ai_fleet,
        "inspect_ollama_loaded_models",
        lambda: {"status": "loaded", "loaded_models": [{"name": "gemma4-e4b:latest"}]},
    )
    monkeypatch.setattr(local_ai_fleet, "list_local_model_runtime_status", lambda root: {})

    result = runner.invoke(app, ["local-ai", "recommend", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["action_id"] == "stop_before_switch"
    assert payload["recommended_command"] == "devflow local-ai stop-all --dry-run --include-ollama --json"


def test_inspect_ollama_loaded_models_uses_api_ps(monkeypatch) -> None:
    from devflow.control_room import local_ai_fleet

    seen_urls: list[str] = []

    def fake_urlopen(url: str, timeout: float) -> _MockResponse:
        seen_urls.append(url)
        assert timeout == 1.0
        return _MockResponse({"models": [{"name": "gemma4-e4b:latest"}]})

    monkeypatch.setattr(local_ai_fleet.urllib.request, "urlopen", fake_urlopen)

    payload = local_ai_fleet.inspect_ollama_loaded_models()

    assert seen_urls == ["http://127.0.0.1:11434/api/ps"]
    assert payload["status"] == "loaded"
    assert payload["loaded_models"][0]["name"] == "gemma4-e4b:latest"


def test_inspect_ollama_installed_models_uses_api_tags(monkeypatch) -> None:
    from devflow.control_room import local_ai_fleet

    seen_urls: list[str] = []

    def fake_urlopen(url: str, timeout: float) -> _MockResponse:
        seen_urls.append(url)
        assert timeout == 1.0
        return _MockResponse({"models": [{"name": "gemma4-e4b:latest"}]})

    monkeypatch.setattr(local_ai_fleet.urllib.request, "urlopen", fake_urlopen)

    payload = local_ai_fleet.inspect_ollama_installed_models()

    assert seen_urls == ["http://127.0.0.1:11434/api/tags"]
    assert payload["status"] == "available"
    assert payload["installed_models"][0]["name"] == "gemma4-e4b:latest"


def test_start_ollama_model_posts_api_generate_with_tiny_payload(monkeypatch) -> None:
    import json as _json
    import urllib.request

    from devflow.control_room import local_ai_fleet

    seen_requests: list[tuple[str, str | None, float | None]] = []

    def fake_urlopen(request: urllib.request.Request, timeout: float | None = None) -> _MockResponse:
        payload = _json.loads(request.data.decode("utf-8")) if request.data else {}
        seen_requests.append((request.full_url, request.get_method(), timeout))
        assert payload["model"] == "gemma4-e4b:latest"
        assert payload["keep_alive"] == "1m"
        assert any(name.lower() == "content-type" and value == "application/json" for name, value in request.header_items())
        return _MockResponse({})

    monkeypatch.setattr(local_ai_fleet.urllib.request, "urlopen", fake_urlopen)

    result = local_ai_fleet.start_ollama_model("gemma4-e4b:latest")

    assert seen_requests == [("http://127.0.0.1:11434/api/generate", "POST", 90.0)]
    assert result["status"] == "started"
    assert result["provider"] == "ollama"
    assert result["model"] == "gemma4-e4b:latest"
    assert result["base_url"] == "http://127.0.0.1:11434"


def test_local_ai_stop_all_dry_run_delegates_to_existing_server_helper(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from devflow.control_room import local_ai_command

    calls: list[dict[str, object]] = []

    def fake_stop(root: Path, **kwargs: object) -> dict[str, object]:
        calls.append({"root": root, **kwargs})
        return {"action": "stop", "status": "would_stop", "processes": []}

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(local_ai_command.local_model_server, "stop_local_model_servers", fake_stop)

    result = runner.invoke(app, ["local-ai", "stop-all", "--dry-run", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "would_stop"
    assert calls == [
        {
            "root": tmp_path,
            "include_ollama": False,
            "dry_run": True,
            "timeout_seconds": 15.0,
            "force_after_timeout": True,
        }
    ]


def test_local_ai_nightly_dry_run_json_has_three_phases_and_only_dry_run_steps(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from devflow.control_room import local_ai_fleet

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(local_ai_fleet, "load_expected_local_model_manifest", _manifest)

    result = runner.invoke(app, ["local-ai", "nightly-dry-run", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["plan_name"] == "nightly-dry-run-local-ai"
    assert payload["dry_run"] is True
    phases = payload["phases"]
    assert len(phases) == 3
    assert payload["action_count"] == 7

    steps = [step for phase in phases for step in phase["steps"]]
    assert [step["step_id"] for step in steps] == [
        "start_qwen",
        "produce_worker_packets",
        "stop_qwen",
        "start_gemma",
        "run_scout_wave",
        "stop_gemma",
        "restart_qwen_for_review",
    ]
    assert all(step["dry_run"] is True for step in steps)
    assert all(step["will_call_model"] is False for step in steps)
    assert all("--dry-run" in step["command"] for step in steps if step["scope"] != "packet-generation")
    assert steps[1]["command"] == "devflow task packet <task-id> --json"
    assert steps[0]["command"] == "devflow local-ai switch supervisor --dry-run --json"
    assert steps[3]["command"] == "devflow local-ai switch scout --dry-run --json"
    assert steps[4]["command"] == "devflow local-ai run-worker-wave <wave-file> --concurrency 1 --dry-run --json"
    assert "Scout capacity is unmeasured" in "\n".join(payload["warnings"])


def test_local_ai_nightly_dry_run_includes_qwen_gemma_sequence_with_scoped_phases(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from devflow.control_room import local_ai_fleet

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(local_ai_fleet, "load_expected_local_model_manifest", _manifest)

    result = runner.invoke(app, ["local-ai", "nightly-dry-run", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    phase_titles = [phase["phase_id"] for phase in payload["phases"]]
    assert phase_titles == ["qwen-wave", "gemma-wave", "qwen-review"]
    assert payload["phases"][0]["steps"][0]["command"].startswith("devflow local-ai switch supervisor")
    assert payload["phases"][1]["steps"][1]["command"].startswith("devflow local-ai run-worker-wave")
    assert payload["phases"][2]["steps"][0]["command"].startswith("devflow local-ai switch supervisor")


def test_local_ai_nightly_dry_run_uses_measured_capacity_in_command(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from devflow.control_room import local_ai_fleet

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(local_ai_fleet, "load_expected_local_model_manifest", _manifest)
    _write_latest_capacity_report(tmp_path, status="success", max_safe_concurrency=3)

    result = runner.invoke(app, ["local-ai", "nightly-dry-run", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    run_step = payload["phases"][1]["steps"][1]
    assert run_step["command"] == "devflow local-ai run-worker-wave <wave-file> --concurrency 3 --dry-run --json"
    assert all("unmeasured" not in warning for warning in payload["warnings"])


def test_local_ai_scout_capacity_dry_run_json(tmp_path: Path, monkeypatch) -> None:
    from devflow.control_room import local_ai_fleet

    packet_path_a, task_a = _write_task_and_packet(tmp_path, "task-cap-a", "Capacity packet A")
    packet_path_b, task_b = _write_task_and_packet(tmp_path, "task-cap-b", "Capacity packet B")
    wave_path = tmp_path / "cap-wave.json"
    wave_payload = [
        str(packet_path_a.relative_to(tmp_path)),
        {"packet": str(packet_path_b.relative_to(tmp_path))},
    ]
    wave_path.write_text(json.dumps(wave_payload, indent=2), encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        local_ai_fleet,
        "inspect_ollama_loaded_models",
        lambda base_url="http://127.0.0.1:11434": {"status": "loaded", "loaded_models": [{"name": "gemma4-e4b:latest"}]},
    )

    result = runner.invoke(app, ["local-ai", "scout-capacity", "cap-wave.json", "--dry-run", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["mode"] == "scout-capacity"
    assert payload["dry_run"] is True
    assert payload["status"] == "ready"
    assert payload["candidates"] == [1, 2, 3]
    assert payload["passes"] == 2
    assert payload["warmup"] == 1
    assert payload["model"] == "gemma4-e4b:latest"
    assert payload["base_url"] == "http://127.0.0.1:11434"
    assert payload["loaded_ollama_models"]["status"] == "loaded"
    assert payload["wave_packets"] == 2
    assert payload["candidate_results"][0]["candidate"] == 1
    assert payload["candidate_results"][0]["status"] == "ready"


def test_local_ai_scout_capacity_dry_run_text_exits_zero(tmp_path: Path, monkeypatch) -> None:
    from devflow.control_room import local_ai_fleet

    packet_path, _task = _write_task_and_packet(tmp_path, "task-cap-text", "Capacity text preview")
    wave_path = tmp_path / "cap-wave-text.json"
    wave_path.write_text(json.dumps([str(packet_path.relative_to(tmp_path))], indent=2), encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        local_ai_fleet,
        "inspect_ollama_loaded_models",
        lambda base_url="http://127.0.0.1:11434": {"status": "idle", "loaded_models": []},
    )

    result = runner.invoke(app, ["local-ai", "scout-capacity", "cap-wave-text.json", "--dry-run"])

    assert result.exit_code == 0, result.output
    assert "status: ready" in result.output


def test_local_ai_scout_capacity_rejects_candidates_without_baseline(
    tmp_path: Path,
    monkeypatch,
) -> None:
    packet_path, _task = _write_task_and_packet(tmp_path, "task-cap-no-baseline", "Capacity no baseline")
    wave_path = tmp_path / "cap-wave-no-baseline.json"
    wave_path.write_text(json.dumps([str(packet_path.relative_to(tmp_path))], indent=2), encoding="utf-8")

    monkeypatch.chdir(tmp_path)

    result = runner.invoke(
        app,
        [
            "local-ai",
            "scout-capacity",
            "cap-wave-no-baseline.json",
            "--dry-run",
            "--candidate",
            "2",
            "--json",
        ],
    )

    assert result.exit_code != 0
    assert "include 1" in result.output


def test_local_ai_scout_capacity_apply_json_passes_then_downgrades(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from devflow.control_room import local_ai_fleet
    from devflow.control_room import local_packet_worker

    packet_path, task = _write_task_and_packet(tmp_path, "task-cap-apply", "Capacity packet apply")
    wave_path = tmp_path / "cap-wave-apply.json"
    wave_payload = [str(packet_path.relative_to(tmp_path))]
    wave_path.write_text(json.dumps(wave_payload, indent=2), encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        local_ai_fleet,
        "inspect_ollama_loaded_models",
        lambda base_url="http://127.0.0.1:11434": {"status": "loaded", "loaded_models": [{"name": "gemma4-e4b:latest"}]},
    )

    calls: list[str] = []

    def fake_run_local_packet_review(
        *,
        task_id: str,
        root: Path | None = None,
        max_packet_chars: int = 200_000,
        **kwargs,
    ) -> dict[str, Path | str | object]:
        call_index = len(calls)
        calls.append(task_id)
        run_id = f"run-{len(calls)}"
        evidence_dir = tmp_path / ".devflow" / "tasks" / task_id / "local-model-runs" / run_id
        response_path = evidence_dir / "response.md"
        response_path.parent.mkdir(parents=True, exist_ok=True)
        response_path.write_text("" if call_index else "valid review output", encoding="utf-8")
        return {
            "run_id": run_id,
            "evidence_dir": evidence_dir,
            "response_path": response_path,
        }

    monkeypatch.setattr(local_packet_worker, "run_local_packet_review", fake_run_local_packet_review)

    result = runner.invoke(
        app,
        [
            "local-ai",
            "scout-capacity",
            "cap-wave-apply.json",
            "--apply",
            "--passes",
            "1",
            "--warmup",
            "0",
            "--candidate",
            "1",
            "--candidate",
            "2",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["mode"] == "scout-capacity"
    assert payload["dry_run"] is False
    assert payload["status"] == "success"
    assert payload["max_safe_concurrency"] == 1
    assert payload["candidate_results"][0]["status"] == "passed"
    assert payload["candidate_results"][1]["status"] == "failed"
    assert payload["candidate_results"][1]["failure_counts"]["output_quality_failure_count"] == 1
    assert payload["failure_counts"]["output_quality_failure_count"] >= 1
    assert len(calls) == 2
    assert "latest_report_path" in payload
    assert "run_report_path" in payload
    assert Path(payload["latest_report_path"]).exists()
    assert Path(payload["run_report_path"]).exists()


def test_local_ai_scout_capacity_apply_rejects_non_target_loaded_without_model_calls(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from devflow.control_room import local_ai_fleet
    from devflow.control_room import local_packet_worker

    packet_path, _task = _write_task_and_packet(tmp_path, "task-cap-loaded", "Capacity loaded guard")
    wave_path = tmp_path / "cap-wave-loaded.json"
    wave_path.write_text(json.dumps([str(packet_path.relative_to(tmp_path))]), encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        local_ai_fleet,
        "inspect_ollama_loaded_models",
        lambda base_url="http://127.0.0.1:11434": {
            "status": "loaded",
            "loaded_models": [{"name": "gemma4-e4b:latest"}, {"name": "qwen:latest"}],
        },
    )
    calls: list[str] = []

    def fake_run_local_packet_review(**kwargs: object) -> dict[str, object]:
        calls.append(str(kwargs.get("task_id")))
        return {}

    monkeypatch.setattr(local_packet_worker, "run_local_packet_review", fake_run_local_packet_review)

    result = runner.invoke(
        app,
        [
            "local-ai",
            "scout-capacity",
            "cap-wave-loaded.json",
            "--apply",
            "--passes",
            "1",
            "--warmup",
            "0",
            "--candidate",
            "1",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "failed"
    assert payload["max_safe_concurrency"] == 0
    assert payload["loaded_model_state_ok"] is False
    assert payload["failure_counts"]["loaded_model_failure_count"] == 1
    assert payload["candidate_results"][0]["attempts"] == 0
    assert calls == []


def test_local_ai_run_scout_pack_dry_run_json(
    tmp_path: Path,
    monkeypatch,
) -> None:
    packet_path, task = _write_task_and_packet(tmp_path, "task-scout-1", "Scout packet test")
    packet_relative = packet_path.relative_to(tmp_path).as_posix()
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["local-ai", "run-scout-pack", packet_relative, "--dry-run", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["schema_version"] == 1
    assert payload["mode"] == "run-scout-pack"
    assert payload["dry_run"] is True
    assert payload["status"] == "ready"
    assert payload["task_id"] == task.id
    assert payload["worker_profile"] == "Gemma E4B"
    assert payload["authority"] == "read-only"
    assert payload["packet_path"] == packet_relative
    assert payload["will_call_model"] is False


def test_local_ai_run_scout_pack_apply_json_calls_packet_worker(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from devflow.control_room import local_packet_worker

    packet_path, task = _write_task_and_packet(tmp_path, "task-scout-2", "Scout packet apply test")
    packet_relative = packet_path.relative_to(tmp_path).as_posix()
    monkeypatch.chdir(tmp_path)
    call_count = []

    def fake_run_local_packet_review(
        *,
        task_id: str,
        root: Path | None = None,
        max_packet_chars: int = 200_000,
        **kwargs,
    ) -> dict[str, Path | str | object]:
        call_count.append((task_id, root, max_packet_chars, kwargs))
        return {
            "run_id": "run-local",
            "evidence_dir": tmp_path / ".devflow" / "tasks" / task_id / "local-model-runs" / "mock",
            "response_path": tmp_path / ".devflow" / "tasks" / task_id / "local-model-runs" / "mock" / "response.md",
        }

    monkeypatch.setattr(local_packet_worker, "run_local_packet_review", fake_run_local_packet_review)

    result = runner.invoke(app, ["local-ai", "run-scout-pack", packet_relative, "--apply", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["mode"] == "run-scout-pack"
    assert payload["dry_run"] is False
    assert payload["status"] == "success"
    assert payload["task_id"] == task.id
    assert payload["run_id"] == "run-local"
    assert payload["will_call_model"] is True
    assert len(call_count) == 1
    called_task_id, called_root, called_max_chars, _called_kwargs = call_count[0]
    assert called_task_id == task.id
    assert called_root == tmp_path
    assert called_max_chars == 200_000
    assert _called_kwargs["model"] == "gemma4-e4b:latest"
    assert _called_kwargs["base_url"] == "http://127.0.0.1:11434/v1"
    assert _called_kwargs["timeout_seconds"] == 120.0


def test_local_ai_run_worker_wave_dry_run_json(
    tmp_path: Path,
    monkeypatch,
) -> None:
    packet_path_a, task_a = _write_task_and_packet(tmp_path, "task-wave-a", "Wave packet A")
    packet_path_b, task_b = _write_task_and_packet(tmp_path, "task-wave-b", "Wave packet B")
    wave_path = tmp_path / "wave.json"
    wave_payload = [
        str(packet_path_a.relative_to(tmp_path)),
        {"packet": str(packet_path_b.relative_to(tmp_path)), "note": "secondary"},
    ]
    wave_path.write_text(json.dumps(wave_payload, indent=2), encoding="utf-8")

    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["local-ai", "run-worker-wave", "wave.json", "--dry-run", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["mode"] == "run-worker-wave"
    assert payload["dry_run"] is True
    assert payload["status"] == "success"
    assert payload["concurrency"] == 1
    assert payload["wave_path"] == "wave.json"
    assert len(payload["results"]) == 2
    assert payload["results"][0]["task_id"] == task_a.id
    assert payload["results"][0]["status"] == "ready"
    assert payload["results"][0]["will_call_model"] is False
    assert payload["results"][1]["task_id"] == task_b.id
    assert payload["results"][1]["status"] == "ready"


def test_local_ai_run_worker_wave_apply_json_uses_local_packet_worker(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from devflow.control_room import local_packet_worker

    packet_path_a, task_a = _write_task_and_packet(tmp_path, "task-wave-apply-a", "Wave apply packet A")
    packet_path_b, task_b = _write_task_and_packet(tmp_path, "task-wave-apply-b", "Wave apply packet B")
    wave_path = tmp_path / "wave-apply.json"
    wave_payload = [
        str(packet_path_a.relative_to(tmp_path)),
        {"packet_path": str(packet_path_b.relative_to(tmp_path))},
    ]
    wave_path.write_text(json.dumps(wave_payload, indent=2), encoding="utf-8")

    monkeypatch.chdir(tmp_path)

    def fake_run_local_packet_review(
        *,
        task_id: str,
        root: Path | None = None,
        max_packet_chars: int = 200_000,
        **kwargs,
    ) -> dict[str, Path | str | object]:
        return {
            "run_id": f"run-{task_id}",
            "evidence_dir": tmp_path / ".devflow" / "tasks" / task_id / "local-model-runs" / "mock",
            "response_path": tmp_path / ".devflow" / "tasks" / task_id / "local-model-runs" / "mock" / "response.md",
        }

    monkeypatch.setattr(local_packet_worker, "run_local_packet_review", fake_run_local_packet_review)

    result = runner.invoke(app, ["local-ai", "run-worker-wave", "wave-apply.json", "--apply", "--concurrency", "1", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "success"
    assert payload["results"][0]["task_id"] == task_a.id
    assert payload["results"][0]["status"] == "success"
    assert payload["results"][0]["run_id"] == f"run-{task_a.id}"
    assert payload["results"][1]["task_id"] == task_b.id
    assert payload["results"][1]["status"] == "success"
    assert payload["results"][1]["run_id"] == f"run-{task_b.id}"


def test_local_ai_run_worker_wave_auto_concurrency_uses_measured_report(
    tmp_path: Path,
    monkeypatch,
) -> None:
    packet_path_a, _task_a = _write_task_and_packet(tmp_path, "task-auto-a", "Wave auto packet")
    wave_path = tmp_path / "wave-auto.json"
    wave_path.write_text(json.dumps([str(packet_path_a.relative_to(tmp_path))], indent=2), encoding="utf-8")

    _write_latest_capacity_report(tmp_path, status="success", max_safe_concurrency=2)
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["local-ai", "run-worker-wave", "wave-auto.json", "--dry-run", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["concurrency"] == 2


def test_local_ai_run_worker_wave_rejects_explicit_over_cap(
    tmp_path: Path,
    monkeypatch,
) -> None:
    wave_path = tmp_path / "wave.json"
    packet_path, _task = _write_task_and_packet(tmp_path, "task-wave-over", "Wave packet")
    wave_path.write_text(json.dumps([str(packet_path.relative_to(tmp_path))]), encoding="utf-8")

    _write_latest_capacity_report(tmp_path, status="success", max_safe_concurrency=1)
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["local-ai", "run-worker-wave", "wave.json", "--apply", "--concurrency", "2", "--json"])

    assert result.exit_code != 0
    assert "exceeds measured safe concurrency" in result.output


def test_local_ai_run_worker_wave_apply_rejects_after_failed_capacity_one(
    tmp_path: Path,
    monkeypatch,
) -> None:
    packet_path, _task = _write_task_and_packet(tmp_path, "task-wave-failed-cap", "Wave failed cap")
    wave_path = tmp_path / "wave-failed-cap.json"
    wave_path.write_text(json.dumps([str(packet_path.relative_to(tmp_path))]), encoding="utf-8")

    _write_latest_capacity_report(tmp_path, status="failed", max_safe_concurrency=0)
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["local-ai", "run-worker-wave", "wave-failed-cap.json", "--apply", "--json"])

    assert result.exit_code != 0
    assert "failed at concurrency 1" in result.output


def test_local_ai_run_worker_wave_apply_preserves_wave_order_with_concurrency_2(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from devflow.control_room import local_packet_worker

    packet_path_a, task_a = _write_task_and_packet(tmp_path, "task-wave-order-a", "Wave order packet A")
    packet_path_b, task_b = _write_task_and_packet(tmp_path, "task-wave-order-b", "Wave order packet B")
    packet_path_c, task_c = _write_task_and_packet(tmp_path, "task-wave-order-c", "Wave order packet C")
    wave_path = tmp_path / "wave-order.json"
    wave_payload = [
        str(packet_path_a.relative_to(tmp_path)),
        {"packet": str(packet_path_b.relative_to(tmp_path))},
        str(packet_path_c.relative_to(tmp_path)),
    ]
    wave_path.write_text(json.dumps(wave_payload, indent=2), encoding="utf-8")

    def fake_run_local_packet_review(
        *,
        task_id: str,
        root: Path | None = None,
        max_packet_chars: int = 200_000,
        **kwargs,
    ) -> dict[str, Path | str | object]:
        return {
            "run_id": f"run-{task_id}",
            "evidence_dir": tmp_path / ".devflow" / "tasks" / task_id / "local-model-runs" / "mock",
            "response_path": tmp_path / ".devflow" / "tasks" / task_id / "local-model-runs" / "mock" / "response.md",
        }

    monkeypatch.setattr(local_packet_worker, "run_local_packet_review", fake_run_local_packet_review)
    _write_latest_capacity_report(tmp_path, status="success", max_safe_concurrency=2)
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(
        app,
        [
            "local-ai",
            "run-worker-wave",
            "wave-order.json",
            "--apply",
            "--concurrency",
            "2",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "success"
    assert payload["concurrency"] == 2
    assert [item["task_id"] for item in payload["results"]] == [task_a.id, task_b.id, task_c.id]
    run_ids = [item["run_id"] for item in payload["results"]]
    assert len(set(run_ids)) == len(run_ids)
    assert run_ids == [f"run-{task_a.id}", f"run-{task_b.id}", f"run-{task_c.id}"]


def test_local_ai_switch_supervisor_dry_run_composes_stop_and_start(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from devflow.control_room import local_ai_command
    from devflow.control_room import local_ai_fleet

    stop_calls: list[dict[str, object]] = []
    start_calls: list[dict[str, object]] = []

    def fake_stop(root: Path, **kwargs: object) -> dict[str, object]:
        stop_calls.append({"root": root, **kwargs})
        return {
            "action": "stop",
            "status": "would_stop",
            "processes": [
                {
                    "pid": 77,
                    "kind": "llama-server",
                    "provider": "ornith-9b",
                    "model": "ornith-9b",
                    "alias": None,
                    "port": 8085,
                }
            ],
        }

    def fake_start(root: Path, profile: str, **kwargs: object) -> dict[str, Any]:
        start_calls.append({"root": root, "profile": profile, **kwargs})
        return {
            "action": "start",
            "status": "would_start",
            "server": profile,
            "provider": "qwen36-27b-q5-mtp",
            "model": "qwen36-27b-q5-mtp",
            "base_url": "http://127.0.0.1:8083/v1",
            "port": 8083,
            "ready": None,
            "pid": None,
        }

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(local_ai_fleet, "load_expected_local_model_manifest", _manifest)
    monkeypatch.setattr(local_ai_command.local_model_server, "stop_local_model_servers", fake_stop)
    monkeypatch.setattr(local_ai_command.local_model_server, "start_local_model_server", fake_start)

    result = runner.invoke(app, ["local-ai", "switch", "supervisor", "--dry-run", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["role"] == "supervisor"
    assert payload["status"] == "would_start"
    assert payload["dry_run"] is True
    assert payload["apply"] is False
    assert payload["model"] == "qwen36-27b-q5-mtp"
    assert payload["provider"] == "qwen36-27b-q5-mtp"
    assert payload["port"] == 8083
    assert payload["include_ollama_stop"] is False
    assert payload["stopped_targets"] == [
        {"pid": 77, "kind": "llama-server", "provider": "ornith-9b", "model": "ornith-9b", "alias": None, "port": 8085},
    ]
    assert payload["started_target"] == {
        "status": "would_start",
        "server_id": "qwen36-27b-q5-mtp",
        "provider": "qwen36-27b-q5-mtp",
        "model": "qwen36-27b-q5-mtp",
        "base_url": "http://127.0.0.1:8083/v1",
        "port": 8083,
        "pid": None,
        "ready": None,
    }
    assert stop_calls == [
        {
            "root": tmp_path,
            "include_ollama": False,
            "dry_run": True,
            "timeout_seconds": 15.0,
        },
    ]
    assert start_calls == [
        {
            "root": tmp_path,
            "profile": "qwen36-27b-q5-mtp",
            "dry_run": True,
            "wait_for_ready": False,
        }
    ]


def test_local_ai_switch_scout_returns_setup_needed_when_ollama_model_not_ready(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from devflow.control_room import local_ai_command
    from devflow.control_room import local_ai_fleet

    stop_calls: list[dict[str, object]] = []

    def fake_stop(root: Path, **kwargs: object) -> dict[str, object]:
        stop_calls.append({"root": root, **kwargs})
        return {"action": "stop", "status": "would_stop", "processes": []}

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(local_ai_fleet, "load_expected_local_model_manifest", _manifest)
    monkeypatch.setattr(local_ai_command.local_model_server, "stop_local_model_servers", fake_stop)
    monkeypatch.setattr(
        local_ai_fleet,
        "inspect_ollama_loaded_models",
        lambda base_url="http://127.0.0.1:11434": {"status": "idle", "loaded_models": []},
    )
    monkeypatch.setattr(
        local_ai_fleet,
        "inspect_ollama_installed_models",
        lambda base_url="http://127.0.0.1:11434": {"status": "empty", "installed_models": []},
    )

    result = runner.invoke(app, ["local-ai", "switch", "scout", "--apply", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["role"] == "scout"
    assert payload["status"] == "setup_needed"
    assert payload["dry_run"] is False
    assert payload["apply"] is True
    assert payload["model"] == "gemma4-e4b:latest"
    assert payload["provider"] == "ollama"
    assert payload["port"] == 11434
    assert payload["include_ollama_stop"] is False
    assert payload["stop_skipped"] is True
    assert payload["started_target"] is None
    assert payload["stopped_targets"] == []
    assert stop_calls == []
    assert any("not currently available in the Ollama runtime" in warning for warning in payload["warnings"])
    assert any("No stop was applied" in warning for warning in payload["warnings"])


def test_local_ai_switch_scout_dry_run_returns_would_start_when_model_is_installed_but_unloaded(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from devflow.control_room import local_ai_command
    from devflow.control_room import local_ai_fleet

    stop_calls: list[dict[str, object]] = []

    def fake_stop(root: Path, **kwargs: object) -> dict[str, object]:
        stop_calls.append({"root": root, **kwargs})
        return {"action": "stop", "status": "would_stop", "processes": []}

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(local_ai_fleet, "load_expected_local_model_manifest", _manifest)
    monkeypatch.setattr(local_ai_command.local_model_server, "stop_local_model_servers", fake_stop)
    monkeypatch.setattr(
        local_ai_fleet,
        "inspect_ollama_loaded_models",
        lambda base_url="http://127.0.0.1:11434": {"status": "idle", "loaded_models": []},
    )
    monkeypatch.setattr(
        local_ai_fleet,
        "inspect_ollama_installed_models",
        lambda base_url="http://127.0.0.1:11434": {
            "status": "available",
            "installed_models": [{"name": "gemma4-e4b:latest"}],
        },
    )

    result = runner.invoke(app, ["local-ai", "switch", "scout", "--dry-run", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "would_start"
    assert payload["role"] == "scout"
    assert payload["started_target"] is None
    assert payload["include_ollama_stop"] is False
    assert payload["stop_skipped"] is False
    assert stop_calls == [
        {
            "root": tmp_path,
            "include_ollama": False,
            "dry_run": True,
            "timeout_seconds": 15.0,
        }
    ]
    assert all("loaded with other Ollama models" not in warning for warning in payload["warnings"])
    assert all("not currently available in the Ollama runtime" not in warning for warning in payload["warnings"])


def test_local_ai_switch_scout_apply_starts_installed_ollama_target(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from devflow.control_room import local_ai_command
    from devflow.control_room import local_ai_fleet

    stop_calls: list[dict[str, object]] = []

    def fake_stop(root: Path, **kwargs: object) -> dict[str, object]:
        stop_calls.append({"root": root, **kwargs})
        return {"action": "stop", "status": "would_stop", "processes": []}

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(local_ai_fleet, "load_expected_local_model_manifest", _manifest)
    monkeypatch.setattr(local_ai_command.local_model_server, "stop_local_model_servers", fake_stop)
    monkeypatch.setattr(
        local_ai_fleet,
        "inspect_ollama_loaded_models",
        lambda base_url="http://127.0.0.1:11434": {"status": "idle", "loaded_models": []},
    )
    monkeypatch.setattr(
        local_ai_fleet,
        "inspect_ollama_installed_models",
        lambda base_url="http://127.0.0.1:11434": {
            "status": "available",
            "installed_models": [{"name": "gemma4-e4b:latest"}],
        },
    )
    monkeypatch.setattr(
        local_ai_fleet,
        "start_ollama_model",
        lambda model_id, **kwargs: {
            "status": "started",
            "provider": "ollama",
            "model": model_id,
            "base_url": kwargs.get("base_url", "http://127.0.0.1:11434"),
        },
    )

    result = runner.invoke(app, ["local-ai", "switch", "scout", "--apply", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "started"
    assert payload["role"] == "scout"
    assert payload["started_target"] == {
        "status": "started",
        "provider": "ollama",
        "model": "gemma4-e4b:latest",
        "base_url": "http://127.0.0.1:11434",
        "port": 11434,
    }
    assert payload["include_ollama_stop"] is False
    assert payload["stop_skipped"] is True
    assert stop_calls == []
    assert any("in Ollama tags; apply is attempting to load it" in warning for warning in payload["warnings"])


def test_local_ai_switch_supervisor_dry_run_includes_ollama_stop_when_model_loaded(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from devflow.control_room import local_ai_command
    from devflow.control_room import local_ai_fleet

    stop_calls: list[dict[str, object]] = []

    def fake_stop(root: Path, **kwargs: object) -> dict[str, object]:
        stop_calls.append({"root": root, **kwargs})
        return {
            "action": "stop",
            "status": "would_stop",
            "processes": [
                {
                    "pid": 88,
                    "kind": "ollama",
                    "provider": "local",
                    "model": None,
                    "alias": None,
                    "port": 11434,
                }
            ],
        }

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(local_ai_fleet, "load_expected_local_model_manifest", _manifest)
    monkeypatch.setattr(local_ai_command.local_model_server, "stop_local_model_servers", fake_stop)
    monkeypatch.setattr(
        local_ai_command.local_model_server,
        "start_local_model_server",
        lambda root, profile, **kwargs: {
            "action": "start",
            "status": "would_start",
            "server": profile,
            "provider": "qwen36-27b-q5-mtp",
            "model": "qwen36-27b-q5-mtp",
            "base_url": "http://127.0.0.1:8083/v1",
            "port": 8083,
            "ready": None,
            "pid": None,
        },
    )
    monkeypatch.setattr(
        local_ai_fleet,
        "inspect_ollama_loaded_models",
        lambda base_url="http://127.0.0.1:11434": {"status": "loaded", "loaded_models": [{"name": "gemma4-e4b:latest"}]},
    )

    result = runner.invoke(app, ["local-ai", "switch", "supervisor", "--dry-run", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["include_ollama_stop"] is True
    assert stop_calls[0]["include_ollama"] is True


def test_local_ai_switch_scout_dry_run_requires_single_loaded_ollama_target(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from devflow.control_room import local_ai_command
    from devflow.control_room import local_ai_fleet

    stop_calls: list[dict[str, object]] = []

    def fake_stop(root: Path, **kwargs: object) -> dict[str, object]:
        stop_calls.append({"root": root, **kwargs})
        return {
            "action": "stop",
            "status": "would_stop",
            "processes": [
                {
                    "pid": 88,
                    "kind": "ollama",
                    "provider": "local",
                    "model": None,
                    "alias": None,
                    "port": 11434,
                }
            ],
        }

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(local_ai_fleet, "load_expected_local_model_manifest", _manifest)
    monkeypatch.setattr(local_ai_command.local_model_server, "stop_local_model_servers", fake_stop)
    monkeypatch.setattr(
        local_ai_fleet,
        "inspect_ollama_loaded_models",
        lambda base_url="http://127.0.0.1:11434": {
            "status": "loaded",
            "loaded_models": [{"name": "gemma4-e4b:latest"}, {"name": "qwen32:latest"}],
        },
    )
    monkeypatch.setattr(
        local_ai_fleet,
        "inspect_ollama_installed_models",
        lambda base_url="http://127.0.0.1:11434": {
            "status": "available",
            "installed_models": [{"name": "gemma4-e4b:latest"}],
        },
    )

    result = runner.invoke(app, ["local-ai", "switch", "scout", "--dry-run", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "setup_needed"
    assert payload["include_ollama_stop"] is True
    assert payload["stop_skipped"] is False
    assert stop_calls[0]["include_ollama"] is True
    assert any("loaded with other Ollama models" in warning for warning in payload["warnings"])
