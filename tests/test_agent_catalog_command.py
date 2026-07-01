from __future__ import annotations

import json

from devflow.control_room.agent_catalog_command import render_agent_catalog_json, render_agent_catalog_lines


def test_render_agent_catalog_lines_owns_cli_text_sections() -> None:
    payload = {
        "providers": [
            {
                "id": "openrouter",
                "adapter": "openai_compatible",
                "api_key_env_missing": True,
            }
        ],
        "profiles": [
            {
                "id": "planner",
                "provider": "openrouter",
                "model": "anthropic/claude-sonnet-4.6",
                "authority": "advisory",
                "runtime_contract": {"execution_surface": "packet-only"},
            }
        ],
        "hermes_agents": [
            {
                "id": "dfsonnet46",
                "provider": "openrouter",
                "model": "anthropic/claude-sonnet-4.6",
                "hermes_profile": "dfsonnet46",
                "status": "ready",
                "blocked_reason": "",
            }
        ],
        "local_ollama": {
            "status": "ready",
            "unregistered_models": ["qwen3:14b"],
        },
        "local_openai_compatible": {
            "status": "ready",
            "providers": [
                {
                    "id": "qwen36-27b-q5-mtp",
                    "status": "ready",
                    "advertised_models": [{"id": "qwen36-27b-q5-mtp"}],
                    "base_url": "http://127.0.0.1:1234/v1",
                }
            ],
        },
        "local_model_policy": {
            "default_provider_id": None,
            "default_model": None,
            "local_model_concurrency": {"mode": "single-flight"},
        },
    }

    assert render_agent_catalog_lines(payload) == (
        "providers:",
        "- openrouter (openai_compatible) missing-env",
        "profiles:",
        "- planner: openrouter/anthropic/claude-sonnet-4.6 advisory -> packet-only",
        "hermes_agents:",
        "- dfsonnet46: openrouter/anthropic/claude-sonnet-4.6 profile=dfsonnet46 status=ready",
        "local_ollama: ready",
        "unregistered_local_models:",
        "- qwen3:14b",
        "local_openai_compatible: ready",
        "local_model_default: none",
        "local_model_concurrency: single-flight",
        "- qwen36-27b-q5-mtp: ready (1 models, http://127.0.0.1:1234/v1)",
    )
    assert json.loads(render_agent_catalog_json(payload))["providers"][0]["id"] == "openrouter"
