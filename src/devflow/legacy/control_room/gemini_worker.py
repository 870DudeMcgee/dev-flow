from __future__ import annotations

import json
import urllib.request
from typing import Any

from devflow.legacy.control_room.context_pack import build_context_pack
from devflow.legacy.control_room.models import WorkerInput, WorkerResult
from devflow.legacy.control_room.provider_patch_worker import (
    ProviderWorkerSettings,
    ProviderWorkerSpec,
    run_provider_patch_worker,
)


_SPEC = ProviderWorkerSpec(
    adapter_name="gemini",
    header_label="Gemini Worker Execution",
    default_model="gemini-2.5-flash",
    default_base_url="https://generativelanguage.googleapis.com",
    default_api_key_env="GEMINI_API_KEY",
    default_api_key_missing_summary=(
        "Gemini provider API key is not configured. Set api_key_env in provider config "
        "and export the matching environment variable."
    ),
    api_log_label="Gemini API",
    connection_error_target="Gemini agent",
    execution_error_prefix="Gemini execution",
)


class GeminiWorkerAdapter:
    name = "gemini"

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
    url = f"{settings.base_url.rstrip('/')}/v1beta/models/{settings.model}:generateContent"
    data = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": prompt},
                ],
            }
        ],
        "systemInstruction": {
            "parts": [
                {"text": system_instruction},
            ],
        },
        "generationConfig": {
            "temperature": 0.2,
            "responseMimeType": "application/json",
        },
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": api_key,
        },
        method="POST",
    )
    return url, req


def _extract_response_text(response_body: dict[str, Any]) -> str:
    candidates = response_body.get("candidates", [])
    if not candidates:
        raise ValueError("No candidates returned from Gemini generateContent API")
    parts = candidates[0].get("content", {}).get("parts", [])
    if not parts:
        raise ValueError("No parts returned from Gemini candidate content")
    text = parts[0].get("text", "")
    return text if isinstance(text, str) else json.dumps(text)
