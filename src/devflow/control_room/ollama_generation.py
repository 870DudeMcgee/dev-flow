from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from devflow.control_room.agent_registry import AgentDefinition


OllamaEndpoint = Literal["generate", "chat"]

DEFAULT_PATCH_NUM_CTX = 8192
DEFAULT_PATCH_NUM_PREDICT = 4096
DEFAULT_PATCH_TEMPERATURE = 0.2

GEMMA_PATCH_AGENT_IDS = {"gemma4-12b-qat-implementer"}


@dataclass(frozen=True)
class OllamaPatchGenerationSettings:
    endpoint: OllamaEndpoint
    num_ctx: int = DEFAULT_PATCH_NUM_CTX
    num_predict: int = DEFAULT_PATCH_NUM_PREDICT
    temperature: float = DEFAULT_PATCH_TEMPERATURE
    think: bool = False
    format_json: bool = True

    @property
    def endpoint_path(self) -> str:
        return "/api/chat" if self.endpoint == "chat" else "/api/generate"

    @property
    def payload_shape(self) -> str:
        return "native_chat_messages" if self.endpoint == "chat" else "generate_prompt_system"

    def options(self) -> dict[str, int | float]:
        return {
            "num_ctx": self.num_ctx,
            "num_predict": self.num_predict,
            "temperature": self.temperature,
        }


def settings_for_ollama_patch_agent(
    agent_id: str,
    model: str,
    agent: AgentDefinition | None = None,
) -> OllamaPatchGenerationSettings:
    model_name = model.lower()
    if agent_id in GEMMA_PATCH_AGENT_IDS or model_name.startswith("gemma4:"):
        return OllamaPatchGenerationSettings(endpoint="chat")
    return OllamaPatchGenerationSettings(endpoint="generate")


def build_ollama_patch_request_payload(
    *,
    model: str,
    system_instruction: str,
    prompt: str,
    settings: OllamaPatchGenerationSettings,
) -> dict[str, Any]:
    if settings.endpoint == "chat":
        payload: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": prompt},
            ],
            "stream": False,
            "think": settings.think,
            "options": settings.options(),
        }
    else:
        payload = {
            "model": model,
            "prompt": prompt,
            "system": system_instruction,
            "stream": False,
            "options": settings.options(),
        }
    if settings.format_json:
        payload["format"] = "json"
    return payload
