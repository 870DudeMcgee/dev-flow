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
    adapter_name="openai_compatible",
    header_label="OpenAI-Compatible Worker Execution",
    default_model="gpt-4o",
    default_base_url="https://api.openai.com/v1",
    default_api_key_env="OPENAI_API_KEY",
    default_api_key_missing_summary=(
        "OpenAI-compatible provider API key is not configured. Set api_key_env in "
        "provider config and export the matching environment variable."
    ),
    api_log_label="OpenAI-compatible API",
    connection_error_target="OpenAI-compatible agent",
    execution_error_prefix="OpenAI-compatible execution",
)


class OpenAICompatibleWorkerAdapter:
    name = "openai_compatible"

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
    url = f"{settings.base_url.rstrip('/')}/chat/completions"
    data = {
        "model": settings.model,
        "messages": [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    return url, req


def _extract_response_text(response_body: dict[str, Any]) -> str:
    choices = response_body.get("choices", [])
    if not choices:
        raise ValueError("No choices returned from OpenAI-compatible completion API")
    message = choices[0].get("message", {})
    content = message.get("content", "")
    return content if isinstance(content, str) else json.dumps(content)
