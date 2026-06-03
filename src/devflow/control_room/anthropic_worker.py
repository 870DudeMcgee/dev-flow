from __future__ import annotations

import json
import urllib.request
from typing import Any

from devflow.control_room.context_pack import build_context_pack
from devflow.control_room.models import WorkerInput, WorkerResult
from devflow.control_room.provider_patch_worker import (
    ProviderWorkerSettings,
    ProviderWorkerSpec,
    run_provider_patch_worker,
)


_SPEC = ProviderWorkerSpec(
    adapter_name="anthropic_messages",
    header_label="Anthropic Worker Execution",
    default_model="claude-3-5-sonnet-latest",
    default_base_url="https://api.anthropic.com",
    default_api_key_env="ANTHROPIC_API_KEY",
    default_api_key_missing_summary=(
        "Anthropic provider API key is not configured. Set api_key_env in provider "
        "config and export the matching environment variable."
    ),
    api_log_label="Anthropic API",
    connection_error_target="Anthropic agent",
    execution_error_prefix="Anthropic execution",
)


class AnthropicMessagesWorkerAdapter:
    name = "anthropic_messages"

    def run(self, worker_input: WorkerInput) -> WorkerResult:
        return run_provider_patch_worker(
            worker_input,
            spec=_SPEC,
            build_request=_build_request,
            extract_response_text=_extract_response_text,
            context_pack_builder=build_context_pack,
        )


def _build_request(
    settings: ProviderWorkerSettings,
    system_instruction: str,
    prompt: str,
    api_key: str,
) -> tuple[str, urllib.request.Request]:
    url = f"{settings.base_url.rstrip('/')}/v1/messages"
    data = {
        "model": settings.model,
        "max_tokens": 4000,
        "system": system_instruction,
        "messages": [
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )
    return url, req


def _extract_response_text(response_body: dict[str, Any]) -> str:
    content = response_body.get("content", [])
    if not content or content[0].get("type") != "text":
        raise ValueError("No text content returned from Anthropic messages API")
    text = content[0].get("text", "")
    return text if isinstance(text, str) else json.dumps(text)
