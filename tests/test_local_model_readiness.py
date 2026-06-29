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


def _catalog(*, include_fast_provider: bool = True, include_fast_profile: bool = True) -> dict:
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
    if include_fast_provider:
        providers.append(
            {
                "id": "qwen35-mtp",
                "provider": "qwen35-mtp",
                "adapter": "openai_compatible",
                "base_url": "http://127.0.0.1:8080/v1",
                "api_key_env": None,
                "api_key_env_missing": False,
                "enabled": True,
            }
        )
    if include_fast_profile:
        profiles.append(
            {
                "id": "hermes-qwen32",
                "provider": "qwen35-mtp",
                "model": "qwen35-9b-mtp",
                "adapter": "openai_compatible",
                "role": "frontier_planner_architect_reviewer",
                "authority": "advisory",
            }
        )
    return {"providers": providers, "profiles": profiles}


def _inventory(*, fast_status: str = "available") -> dict:
    return {
        "summary": {"default_provider_id": "qwen35-mtp", "default_model": "qwen35-9b-mtp"},
        "rows": [
            {
                "row_id": "profile:hermes-qwen32",
                "kind": "registered_profile",
                "provider_id": "qwen35-mtp",
                "model": "qwen35-9b-mtp",
                "profile_id": "hermes-qwen32",
                "status": fast_status,
            }
        ],
    }


def test_load_expected_local_model_manifest_records_required_v1_lanes() -> None:
    manifest = load_expected_local_model_manifest()

    assert tuple(manifest.lanes) == EXPECTED_LANE_IDS
    fast = manifest.require_lane("hermes-qwen32")
    assert fast.profile_id == "hermes-qwen32"
    assert fast.provider_id == "qwen35-mtp"
    assert fast.model_id == "qwen35-9b-mtp"
    assert fast.base_url == "http://127.0.0.1:8080/v1"
    assert fast.port == 8080
    assert fast.local_server_backed is True
    minimax = manifest.require_lane("hermes-minimaxm3")
    assert minimax.provider_id == "openrouter"
    assert minimax.model_id == "minimax/minimax-m3"


def test_readiness_uses_ram_thresholds_before_claiming_lane_ready() -> None:
    plan = build_local_model_readiness_plan(
        Path.cwd(),
        agent_catalog=_catalog(),
        inventory=_inventory(),
        machine=_machine(16),
    )

    lanes = {lane["lane_id"]: lane for lane in plan["lanes"]}
    assert lanes["hermes-qwen32"]["readiness"] == "ready"
    assert lanes["hermes-qwen32"]["ram_status"] == "ideal"
    assert lanes["hermes-ornith35b"]["readiness"] == "blocked_ram"
    assert lanes["hermes-ornith35b"]["ram_status"] == "insufficient"
    assert lanes["hermes-gemma12b"]["readiness"] == "blocked_ram"


def test_fallback_lanes_keep_manifest_order_and_minimax_runtime() -> None:
    plan = build_local_model_readiness_plan(
        Path.cwd(),
        agent_catalog=_catalog(),
        inventory=_inventory(),
        machine=_machine(96),
    )

    lanes = {lane["lane_id"]: lane for lane in plan["lanes"]}
    assert lanes["hermes-ornith35b"]["fallback_lanes"] == [
        "hermes-ornith9b",
        "hermes-gemma12b",
        "hermes-minimaxm3",
    ]
    assert lanes["hermes-opus48"]["fallback_lanes"] == [
        "hermes-sonnet46",
        "hermes-qwen37plus",
        "hermes-codex-gpt55",
        "hermes-qwen32",
    ]
    assert lanes["hermes-minimaxm3"]["provider_id"] == "openrouter"
    assert lanes["hermes-minimaxm3"]["model_id"] == "minimax/minimax-m3"


def test_provision_commands_register_provider_then_exact_profile() -> None:
    plan = build_local_model_readiness_plan(
        Path.cwd(),
        agent_catalog=_catalog(include_fast_provider=False, include_fast_profile=False),
        inventory={"summary": {}, "rows": []},
        machine=_machine(16),
    )

    fast = next(lane for lane in plan["lanes"] if lane["lane_id"] == "hermes-qwen32")
    assert fast["readiness"] == "needs_provider"
    assert [item["kind"] for item in fast["provision_commands"]] == ["provider", "model"]
    assert fast["provision_commands"][0]["command"] == (
        "devflow agent add-provider qwen35-mtp --adapter openai_compatible "
        "--base-url http://127.0.0.1:8080/v1 --json"
    )
    assert fast["provision_commands"][0]["argv"] == [
        "devflow",
        "agent",
        "add-provider",
        "qwen35-mtp",
        "--adapter",
        "openai_compatible",
        "--base-url",
        "http://127.0.0.1:8080/v1",
        "--json",
    ]
    assert fast["provision_commands"][1]["command"] == (
        "devflow agent add-model --provider qwen35-mtp --model qwen35-9b-mtp "
        "--authority advisory --role frontier_planner_architect_reviewer "
        "--profile-id hermes-qwen32 --json"
    )
    assert fast["provision_commands"][1]["argv"] == [
        "devflow",
        "agent",
        "add-model",
        "--provider",
        "qwen35-mtp",
        "--model",
        "qwen35-9b-mtp",
        "--authority",
        "advisory",
        "--role",
        "frontier_planner_architect_reviewer",
        "--profile-id",
        "hermes-qwen32",
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
    assert minimax["provision_commands"][1]["command"] == (
        "devflow agent add-model --provider openrouter --model minimax/minimax-m3 "
        "--authority advisory --role frontier_planner_architect_reviewer "
        "--profile-id hermes-minimaxm3 --json"
    )
