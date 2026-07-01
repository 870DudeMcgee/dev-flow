from __future__ import annotations

from pathlib import Path

from devflow.control_room.local_model_readiness import (
    EXPECTED_LANE_IDS,
    build_local_model_readiness_plan,
    load_expected_local_model_manifest,
)
from devflow.control_room.machine_capability import MachineCapability


def _machine(memory_gb: int) -> MachineCapability:
    return MachineCapability(
        total_memory_gb=memory_gb,
        machine_class="mac_mini" if memory_gb <= 18 else "workstation",
        max_recommended_weight_class="medium" if memory_gb <= 24 else "heavy",
        local_model_concurrency={
            "mode": "single_flight",
            "max_parallel_local_model_runs": 1,
            "reason": "test",
        },
    )


def _catalog(*, include_qwen36_provider: bool = True, include_qwen36_profile: bool = True) -> dict:
    providers = [
        {
            "id": "openrouter",
            "provider": "openrouter",
            "adapter": "openai_compatible",
            "base_url": "https://openrouter.ai/api/v1",
            "api_key_env": "OPENROUTER_API_KEY",
            "api_key_env_missing": False,
            "enabled": True,
        }
    ]
    profiles = [
        {
            "id": "hermes-minimaxm3",
            "provider": "openrouter",
            "model": "minimax/minimax-m3",
            "adapter": "openai_compatible",
            "role": "frontier_planner_architect_reviewer",
            "authority": "advisory",
        }
    ]
    if include_qwen36_provider:
        providers.append(
            {
                "id": "qwen36-27b-q5-mtp",
                "provider": "qwen36-27b-q5-mtp",
                "adapter": "openai_compatible",
                "base_url": "http://127.0.0.1:8083/v1",
                "api_key_env": None,
                "api_key_env_missing": False,
                "enabled": True,
            }
        )
    if include_qwen36_profile:
        profiles.append(
            {
                "id": "hermes-qwen36-27b-q5-mtp",
                "provider": "qwen36-27b-q5-mtp",
                "model": "qwen36-27b-q5-mtp",
                "adapter": "openai_compatible",
                "role": "implementation_worker",
                "authority": "read-only",
            }
        )
    return {"providers": providers, "profiles": profiles}


def _inventory(*, qwen36_status: str = "available") -> dict:
    return {
        "summary": {"default_provider_id": None, "default_model": None, "default_source": "none"},
        "rows": [
            {
                "row_id": "profile:hermes-qwen36-27b-q5-mtp",
                "kind": "registered_profile",
                "provider_id": "qwen36-27b-q5-mtp",
                "model": "qwen36-27b-q5-mtp",
                "profile_id": "hermes-qwen36-27b-q5-mtp",
                "status": qwen36_status,
            }
        ],
    }


def test_load_expected_local_model_manifest_records_required_v1_lanes() -> None:
    manifest = load_expected_local_model_manifest()

    assert tuple(manifest.lanes) == EXPECTED_LANE_IDS
    assert manifest.require_lane("hermes-qwen32-latest").model_id == "qwen32:latest"
    assert manifest.require_lane("hermes-gemma12b-latest").model_id == "gemma12b:latest"
    assert manifest.require_lane("hermes-qwopus-35b").model_id == "qwopus-35b"
    qwen36 = manifest.require_lane("hermes-qwen36-27b-q5-mtp")
    assert qwen36.provider_id == "qwen36-27b-q5-mtp"
    assert qwen36.model_id == "qwen36-27b-q5-mtp"
    assert qwen36.base_url == "http://127.0.0.1:8083/v1"
    assert qwen36.local_server_backed is True
    assert qwen36.role == "frontier_planner_architect_reviewer"
    assert manifest.require_lane("hermes-ornith-35b").provider_id == "ornith-35b"
    assert manifest.require_lane("hermes-ornith-9b").provider_id == "ornith-9b"
    assert manifest.require_lane("hermes-gemma4-e4b").role == "scout"


def test_readiness_uses_ram_thresholds_before_claiming_lane_ready() -> None:
    plan = build_local_model_readiness_plan(
        Path.cwd(),
        agent_catalog=_catalog(),
        inventory=_inventory(),
        machine=_machine(16),
    )

    lanes = {lane["lane_id"]: lane for lane in plan["lanes"]}
    assert lanes["hermes-qwen36-27b-q5-mtp"]["readiness"] == "blocked_ram"
    assert lanes["hermes-qwen36-27b-q5-mtp"]["ram_status"] == "insufficient"
    assert lanes["hermes-qwen32-latest"]["readiness"] == "needs_provider"
    assert lanes["hermes-ornith-35b"]["readiness"] == "blocked_ram"


def test_fallback_lanes_keep_manifest_order_and_minimax_runtime() -> None:
    plan = build_local_model_readiness_plan(
        Path.cwd(),
        agent_catalog=_catalog(),
        inventory=_inventory(),
        machine=_machine(96),
    )

    lanes = {lane["lane_id"]: lane for lane in plan["lanes"]}
    assert lanes["hermes-ornith-35b"]["fallback_lanes"] == [
        "hermes-ornith-9b",
        "hermes-gemma12b-latest",
        "hermes-minimaxm3",
    ]
    assert lanes["hermes-opus48"]["fallback_lanes"] == [
        "hermes-sonnet46",
        "hermes-qwen37plus",
        "hermes-codex-gpt55",
        "hermes-qwen32-latest",
    ]
    assert lanes["hermes-minimaxm3"]["provider_id"] == "openrouter"
    assert lanes["hermes-minimaxm3"]["model_id"] == "minimax/minimax-m3"


def test_provision_commands_register_provider_then_exact_profile() -> None:
    plan = build_local_model_readiness_plan(
        Path.cwd(),
        agent_catalog=_catalog(include_qwen36_provider=False, include_qwen36_profile=False),
        inventory={"summary": {}, "rows": []},
        machine=_machine(96),
    )

    qwen36 = next(lane for lane in plan["lanes"] if lane["lane_id"] == "hermes-qwen36-27b-q5-mtp")
    assert qwen36["readiness"] == "needs_provider"
    assert [item["kind"] for item in qwen36["provision_commands"]] == ["provider", "model"]
    assert qwen36["provision_commands"][0]["command"] == (
        "devflow agent add-provider qwen36-27b-q5-mtp --adapter openai_compatible "
        "--base-url http://127.0.0.1:8083/v1 --json"
    )
    assert qwen36["provision_commands"][1]["command"] == (
        "devflow agent add-model --provider qwen36-27b-q5-mtp --model qwen36-27b-q5-mtp "
        "--authority advisory --role frontier_planner_architect_reviewer "
        "--profile-id hermes-qwen36-27b-q5-mtp --json"
    )


def test_start_commands_use_managed_server_name_not_profile_id() -> None:
    plan = build_local_model_readiness_plan(
        Path.cwd(),
        agent_catalog=_catalog(),
        inventory=_inventory(qwen36_status="unavailable"),
        machine=_machine(96),
    )

    qwen36 = next(lane for lane in plan["lanes"] if lane["lane_id"] == "hermes-qwen36-27b-q5-mtp")
    assert qwen36["start_commands"][0]["command"] == "devflow local-model start qwen36-27b-q5-mtp --replace --json"
    assert qwen36["start_commands"][0]["argv"] == [
        "devflow",
        "local-model",
        "start",
        "qwen36-27b-q5-mtp",
        "--replace",
        "--json",
    ]


def test_provision_commands_include_openrouter_api_key_env_when_provider_is_missing() -> None:
    plan = build_local_model_readiness_plan(
        Path.cwd(),
        agent_catalog={"providers": [], "profiles": []},
        inventory={"summary": {}, "rows": []},
        machine=_machine(96),
    )

    minimax = next(lane for lane in plan["lanes"] if lane["lane_id"] == "hermes-minimaxm3")
    assert minimax["readiness"] == "needs_provider"
    assert minimax["provision_commands"][0]["command"] == (
        "devflow agent add-provider openrouter --adapter openai_compatible "
        "--base-url https://openrouter.ai/api/v1 --api-key-env OPENROUTER_API_KEY --json"
    )


def test_scout_lane_is_not_ready_when_profile_is_missing() -> None:
    catalog = _catalog()
    catalog["providers"].append(
        {
            "id": "ollama",
            "provider": "ollama",
            "adapter": "ollama_chat",
            "base_url": "http://127.0.0.1:11434",
            "api_key_env": None,
            "api_key_env_missing": False,
            "enabled": True,
        }
    )

    plan = build_local_model_readiness_plan(
        Path.cwd(),
        agent_catalog=catalog,
        inventory={"summary": {}, "rows": []},
        machine=_machine(96),
    )
    gemma4 = next(lane for lane in plan["lanes"] if lane["lane_id"] == "hermes-gemma4-e4b")
    assert gemma4["readiness"] == "needs_profile"
    assert gemma4["ready"] is False
    assert gemma4["readiness"] != "ready"
    assert gemma4["provision_commands"][0]["command"] == (
        "devflow agent add-model --provider ollama --model gemma4-e4b:latest --authority read-only --role scout "
        "--profile-id hermes-gemma4-e4b --json"
    )
