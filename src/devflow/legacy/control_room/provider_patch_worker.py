from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from devflow.legacy.control_room.agent_registry import load_agent_registry, load_provider_registry
from devflow.legacy.control_room.context_pack import build_context_pack
from devflow.legacy.control_room.json_utils import repair_and_parse_json
from devflow.legacy.control_room.log_sanitizer import latest_visible_log_line
from devflow.legacy.control_room.models import WorkerInput, WorkerResult
from devflow.legacy.control_room.persistence import atomic_write_text


class ProviderRequestBuilder(Protocol):
    def __call__(
        self,
        settings: ProviderWorkerSettings,
        system_instruction: str,
        prompt: str,
        api_key: str,
    ) -> tuple[str, urllib.request.Request]:
        ...


ProviderResponseExtractor = Callable[[dict[str, Any]], str]
ContextPackBuilder = Callable[[Path, str, str], dict[str, Any]]


@dataclass(frozen=True)
class ProviderWorkerSpec:
    adapter_name: str
    header_label: str
    default_model: str
    default_base_url: str
    default_api_key_env: str
    default_api_key_missing_summary: str
    api_log_label: str
    connection_error_target: str
    execution_error_prefix: str


@dataclass(frozen=True)
class ProviderWorkerSettings:
    agent_id: str | None
    evidence_agent_id: str
    provider_name: str
    model: str
    base_url: str
    timeout_seconds: int
    api_key_env: str


def run_provider_patch_worker(
    worker_input: WorkerInput,
    *,
    spec: ProviderWorkerSpec,
    build_request: ProviderRequestBuilder,
    extract_response_text: ProviderResponseExtractor,
    context_pack_builder: ContextPackBuilder = build_context_pack,
) -> WorkerResult:
    """Run an experimental provider adapter that writes patch evidence only."""
    worker_input.workspace_path.mkdir(parents=True, exist_ok=True)
    worker_input.log_file.parent.mkdir(parents=True, exist_ok=True)

    with worker_input.log_file.open("w", encoding="utf-8") as log:
        log.write(f"=== {spec.header_label} for Task {worker_input.task_id} ===\n")

    settings = _resolve_settings(worker_input, spec)
    api_key = os.environ.get(settings.api_key_env)
    if not api_key:
        if settings.api_key_env != spec.default_api_key_env:
            err_msg = (
                f"Provider '{settings.provider_name}' requires api_key_env "
                f"'{settings.api_key_env}', but that environment variable is not set."
            )
        else:
            err_msg = spec.default_api_key_missing_summary
        _write_log_line(worker_input, err_msg)
        return _result(worker_input, status="worker_failed", summary=err_msg, exit_code=1)

    context_pack = _build_context_pack(worker_input, context_pack_builder)
    system_instruction = _provider_system_instruction()
    prompt = _build_prompt(worker_input, context_pack)
    url, req = build_request(settings, system_instruction, prompt, api_key)

    _write_log_line(
        worker_input,
        f"Connecting to {spec.api_log_label} on {url} "
        f"(model: {settings.model}, timeout: {settings.timeout_seconds}s)...",
    )

    try:
        with urllib.request.urlopen(req, timeout=settings.timeout_seconds) as response:
            res_body = json.loads(response.read().decode("utf-8"))
            response_text = extract_response_text(res_body)
    except urllib.error.URLError as exc:
        err_msg = f"Error connecting to {spec.connection_error_target}: {exc}"
        _write_log_line(worker_input, err_msg)
        return _result(worker_input, status="worker_failed", summary=err_msg, exit_code=1)
    except Exception as exc:
        err_msg = f"{spec.execution_error_prefix} encountered an exception: {exc}"
        _write_log_line(worker_input, err_msg)
        return _result(worker_input, status="worker_failed", summary=err_msg, exit_code=1)

    return write_provider_patch_evidence(worker_input, settings, response_text)


def write_provider_patch_evidence(
    worker_input: WorkerInput,
    settings: ProviderWorkerSettings,
    response_text: str,
) -> WorkerResult:
    """Parse provider JSON and write raw_output/proposal.patch evidence."""
    agent_dir = _agent_dir(worker_input, settings.evidence_agent_id)
    raw_output_path = agent_dir / "raw_output.md"
    patch_file = agent_dir / "proposal.patch"
    atomic_write_text(raw_output_path, response_text)

    try:
        diff_data = repair_and_parse_json(response_text)
        if not isinstance(diff_data, dict):
            raise ValueError("Expected JSON object response.")
    except Exception as exc:
        err_msg = f"JSON parsing of agent response failed: {exc}"
        _write_log_line(worker_input, err_msg)
        _write_log_line(worker_input, f"Raw response preserved at {raw_output_path}")
        return _result(worker_input, status="worker_failed", summary=err_msg, exit_code=1)

    response_status = str(diff_data.get("status", "failed"))
    if response_status != "ready":
        blocked_reason = str(
            diff_data.get("blocked_reason")
            or diff_data.get("reason")
            or "Worker indicated blocked/failed state"
        )
        _write_log_line(
            worker_input,
            f"Worker did not complete successfully. Status: {response_status}. "
            f"Reason: {blocked_reason}",
        )
        return _result(
            worker_input,
            status="blocked" if response_status == "blocked" else "worker_failed",
            summary=blocked_reason,
            exit_code=1,
        )

    diff_text = str(diff_data.get("diff", ""))
    if not diff_text.strip():
        summary = "Worker completed with empty diff"
        _write_log_line(worker_input, "Worker output completed but returned an empty diff.")
        return _result(worker_input, status="complete", summary=summary, exit_code=0)

    atomic_write_text(patch_file, diff_text)
    _write_log_line(worker_input, f"Raw output written to {raw_output_path}")
    _write_log_line(worker_input, f"Proposed patch written to {patch_file}")
    _write_log_line(worker_input, "Worker completed successfully.")
    return _result(
        worker_input,
        status="complete",
        summary="Worker completed successfully",
        exit_code=0,
    )


def _resolve_settings(worker_input: WorkerInput, spec: ProviderWorkerSpec) -> ProviderWorkerSettings:
    agent_id = worker_input.env.get("DEVFLOW_AGENT_ID")
    evidence_agent_id = agent_id or "default_agent"
    provider_name = "unknown"
    model = spec.default_model
    base_url = spec.default_base_url
    timeout = worker_input.timeout_seconds or 300
    api_key_env = spec.default_api_key_env

    if agent_id:
        try:
            registry = load_agent_registry(worker_input.repo_root)
            agent = registry.require_agent(agent_id)
            model = agent.model
            provider_name = agent.provider

            providers = load_provider_registry(worker_input.repo_root)
            provider_def = providers.require_provider(agent.provider)
            if provider_def.base_url:
                base_url = provider_def.base_url
            if provider_def.default_timeout_seconds:
                timeout = provider_def.default_timeout_seconds
            if provider_def.api_key_env:
                api_key_env = provider_def.api_key_env
        except Exception as exc:
            _write_log_line(worker_input, f"Warning resolving agent/provider registry: {exc}")

    return ProviderWorkerSettings(
        agent_id=agent_id,
        evidence_agent_id=evidence_agent_id,
        provider_name=provider_name,
        model=model,
        base_url=base_url,
        timeout_seconds=timeout,
        api_key_env=api_key_env,
    )


def _build_context_pack(
    worker_input: WorkerInput,
    context_pack_builder: ContextPackBuilder,
) -> dict[str, Any]:
    try:
        pack_data = context_pack_builder(worker_input.repo_root, worker_input.task_id, "worker")
        return pack_data.get("context_pack", {})
    except Exception as exc:
        _write_log_line(worker_input, f"Warning generating context pack: {exc}")
        return {}


def _provider_system_instruction() -> str:
    return (
        "You are a software engineer working inside a Dev-Flow isolated workspace. "
        "Analyze the task contract and context, then provide code modifications as a unified diff "
        "in strict JSON format.\n\n"
        "=== OUTPUT SCHEMA ===\n"
        "Output only raw JSON matching this schema (no markdown, no extra text):\n"
        "{\n"
        "  \"status\": \"ready\" | \"blocked\" | \"failed\",\n"
        "  \"diff\": \"string (unified diff format)\",\n"
        "  \"touched_paths\": [\"string\"],\n"
        "  \"risk\": \"low\" | \"medium\" | \"high\" | \"critical\",\n"
        "  \"confidence\": float (0.0 to 1.0)\n"
        "}\n\n"
        "=== DIFF PROTOCOLS ===\n"
        "1. Use standard git unified diff format.\n"
        "2. Context lines must match the target files exactly (character-for-character, including indentation).\n"
        "3. Header paths must match target files (e.g., --- src/foo.py, +++ src/foo.py).\n"
        "4. Do not truncate diff chunks or omit required lines.\n"
        "5. Set status to 'blocked' with a reason if the task cannot be completed safely."
    )


def _build_prompt(worker_input: WorkerInput, context_pack: dict[str, Any]) -> str:
    prompt_lines = [
        f"TASK ID: {worker_input.task_id}",
        f"WORKSPACE: {worker_input.workspace_path.name}",
        "",
        "CONTEXT SOURCES:",
    ]

    for item in context_pack.get("sources_metadata", []):
        if item.get("mode") == "full":
            prompt_lines.append(f"--- File: {item['path']} ---")
            prompt_lines.append(str(item.get("content", "")))
            prompt_lines.append("")

    return "\n".join(prompt_lines)


def _agent_dir(worker_input: WorkerInput, agent_id: str) -> Path:
    agent_dir = worker_input.repo_root / ".devflow" / "tasks" / worker_input.task_id / "agents" / agent_id
    agent_dir.mkdir(parents=True, exist_ok=True)
    return agent_dir


def _write_log_line(worker_input: WorkerInput, message: str) -> None:
    with worker_input.log_file.open("a", encoding="utf-8") as log:
        log.write(f"{message}\n")


def _result(
    worker_input: WorkerInput,
    *,
    status: str,
    summary: str,
    exit_code: int,
) -> WorkerResult:
    return WorkerResult(
        status=status,  # type: ignore[arg-type]
        summary=summary,
        exit_code=exit_code,
        latest_log_line=latest_visible_log_line(worker_input.log_file),
        result_file=worker_input.result_file,
        log_file=worker_input.log_file,
    )
