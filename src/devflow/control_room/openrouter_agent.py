from __future__ import annotations

import json
import os
import re
import signal
import threading
import urllib.error
import urllib.request
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from devflow.control_room.agent_registry import (
    AgentDefinition,
    AgentRegistryError,
    ProviderDefinition,
    is_local_openai_compatible_provider,
    is_remote_advisory_agent,
    is_remote_patch_proposal_agent,
    load_agent_registry,
    load_provider_registry,
)
from devflow.control_room.local_model_server import ensure_local_model_server_for_profile
from devflow.control_room.models import TaskRecord
from devflow.control_room.patch_applier import (
    PatchApplicationError,
    PatchParseError,
    apply_patch_files,
    parse_unified_diff,
)
from devflow.control_room.patch_proposal import inspect_patch_proposal, normalize_hunk_line_counts
from devflow.control_room.paths import absolute_path, relative_path
from devflow.control_room.persistence import atomic_write_text, get_task
from devflow.control_room.supervisor_surface import build_supervisor_packet
from devflow.control_room.task_packet import build_agent_packet


ADVISORY_JOBS = {"gap-analysis", "review", "status"}
SECRET_PATTERN = re.compile(r"sk-[A-Za-z0-9][A-Za-z0-9_-]{6,}")
PATCH_REQUEST_TIMEOUT_SECONDS = 90
PATCH_MAX_TOKENS = 2048
PATCH_REASONING_EFFORT = "minimal"
PATCH_PROMPT_MODE_ENV = "DEVFLOW_OPENROUTER_PATCH_PROMPT_MODE"
PATCH_PROMPT_MODES = {"standard", "minimal"}
DEFAULT_AGENT_PROMPT_MAX_CHARS = 200_000
MINIMAL_PATCH_SNIPPET_MAX_FILES = 6
MINIMAL_PATCH_SNIPPET_MAX_CHARS_PER_FILE = 16_000
MINIMAL_PATCH_SNIPPET_MAX_CHARS_TOTAL = 80_000


class OpenRouterAgentError(ValueError):
    pass


def dry_run_advice(
    *,
    root: Path,
    profile_id: str,
    job: str,
    task_id: str | None = None,
    max_prompt_chars: int = DEFAULT_AGENT_PROMPT_MAX_CHARS,
) -> dict[str, Any]:
    root = root.resolve()
    profile, provider = _load_advisory_profile(root, profile_id)
    _validate_advisory_job(job)
    prompt, truncated = _build_advisory_prompt(root, profile, job=job, task_id=task_id, max_chars=max_prompt_chars)
    run_id = f"dry-run-{profile.id}"
    evidence_dir = _advisory_run_dir(root, task_id, run_id)
    return {
        "schema_version": 1,
        "dry_run": True,
        "status": "planned",
        "run_id": run_id,
        "task_id": task_id,
        "profile_id": profile.id,
        "job": job,
        "provider": profile.provider,
        "model": profile.model,
        "adapter": profile.adapter,
        "provider_base_url": provider.base_url,
        "evidence_dir": relative_path(root, evidence_dir),
        "prompt_chars": len(prompt),
        "prompt_truncated": truncated,
        "will_call_provider": False,
        "safety_flags": _safety_flags(),
    }


def run_advice(
    *,
    root: Path,
    profile_id: str,
    job: str,
    task_id: str | None = None,
    max_prompt_chars: int = DEFAULT_AGENT_PROMPT_MAX_CHARS,
    max_response_chars: int = 200_000,
) -> dict[str, Any]:
    root = root.resolve()
    profile, provider = _load_advisory_profile(root, profile_id)
    _validate_advisory_job(job)
    prompt, truncated = _build_advisory_prompt(root, profile, job=job, task_id=task_id, max_chars=max_prompt_chars)
    run_id = _new_run_id(profile.id)
    evidence_dir = _advisory_run_dir(root, task_id, run_id)
    prompt_path = evidence_dir / "prompt.md"
    response_path = evidence_dir / "response.md"
    raw_response_path = evidence_dir / "response.raw.json"
    metadata_path = evidence_dir / "run.json"
    atomic_write_text(prompt_path, prompt)
    local_model_server_lifecycle: dict[str, Any] | None = None

    api_key_env = provider.api_key_env or _default_api_key_env(provider)
    api_key = os.environ.get(api_key_env)
    if not api_key and not is_local_openai_compatible_provider(provider):
        error = f"Provider '{provider.id}' requires {api_key_env}, but that environment variable is not set."
        payload = _advice_payload(
            root=root,
            status="failed",
            run_id=run_id,
            task_id=task_id,
            profile=profile,
            provider=provider,
            job=job,
            prompt_path=prompt_path,
            response_path=None,
            raw_response_path=None,
            metadata_path=metadata_path,
            prompt_truncated=truncated,
            usage=None,
            recommendations=[],
            error=error,
            will_call_provider=False,
            local_model_server_lifecycle=local_model_server_lifecycle,
        )
        atomic_write_text(metadata_path, json.dumps(payload, indent=2, sort_keys=True) + "\n")
        return payload

    try:
        if is_local_openai_compatible_provider(provider):
            local_model_server_lifecycle = ensure_local_model_server_for_profile(
                root=root,
                provider=profile.provider,
                model=profile.model,
                base_url=provider.base_url,
            )
        response_body = _chat_completion(
            provider=provider,
            model=profile.model,
            system_prompt=_advisory_system_prompt(profile, job),
            user_prompt=prompt,
            api_key=api_key,
        )
        raw_text = _safe_json(response_body, api_key=api_key)
        content = _assistant_content(response_body)
        content = _cap_text(content, max_response_chars)
        recommendations = _extract_recommendations(content)
        atomic_write_text(raw_response_path, raw_text)
        atomic_write_text(response_path, content + ("\n" if content and not content.endswith("\n") else ""))
        payload = _advice_payload(
            root=root,
            status="success",
            run_id=run_id,
            task_id=task_id,
            profile=profile,
            provider=provider,
            job=job,
            prompt_path=prompt_path,
            response_path=response_path,
            raw_response_path=raw_response_path,
            metadata_path=metadata_path,
            prompt_truncated=truncated,
            usage=response_body.get("usage") if isinstance(response_body.get("usage"), dict) else None,
            recommendations=recommendations,
            error=None,
            will_call_provider=True,
            local_model_server_lifecycle=local_model_server_lifecycle,
        )
    except Exception as exc:
        error = _redact(str(exc), api_key=api_key)
        payload = _advice_payload(
            root=root,
            status="failed",
            run_id=run_id,
            task_id=task_id,
            profile=profile,
            provider=provider,
            job=job,
            prompt_path=prompt_path,
            response_path=None,
            raw_response_path=None,
            metadata_path=metadata_path,
            prompt_truncated=truncated,
            usage=None,
            recommendations=[],
            error=error,
            will_call_provider=True,
            local_model_server_lifecycle=local_model_server_lifecycle,
        )
    atomic_write_text(metadata_path, json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return payload


def run_patch_proposal(
    *,
    root: Path,
    task_id: str,
    profile_id: str,
    max_prompt_chars: int = DEFAULT_AGENT_PROMPT_MAX_CHARS,
    max_response_chars: int = 240_000,
) -> dict[str, Any]:
    root = root.resolve()
    profile, provider = _load_patch_profile(root, profile_id)
    task = get_task(root, task_id)
    prompt_mode = _patch_prompt_mode()
    prompt, truncated = _build_patch_prompt(
        root,
        profile,
        task=task,
        prompt_mode=prompt_mode,
        max_chars=max_prompt_chars,
    )
    prompt_chars = len(prompt)
    run_id = _new_run_id(profile.id)
    agent_dir = root / ".devflow" / "tasks" / task.id / "agents" / profile.id
    raw_output_path = agent_dir / "raw_output.md"
    proposal_path = agent_dir / "proposal.patch"
    metadata_path = agent_dir / "run.json"
    result_path = agent_dir / "result.md"
    raw_outputs: list[str] = []

    api_key_env = provider.api_key_env or _default_api_key_env(provider)
    api_key = os.environ.get(api_key_env)
    if not api_key and not is_local_openai_compatible_provider(provider):
        error = f"Provider '{provider.id}' requires {api_key_env}, but that environment variable is not set."
        payload = _patch_payload(
            root=root,
            status="failed",
            run_id=run_id,
            task_id=task.id,
            task_title=task.title,
            profile=profile,
            provider=provider,
            prompt_mode=prompt_mode,
            prompt_chars=prompt_chars,
            prompt_truncated=truncated,
            raw_output_path=None,
            proposal_path=None,
            metadata_path=metadata_path,
            result_path=result_path,
            summary=error,
            error=error,
            usage=None,
            will_call_provider=False,
        )
        atomic_write_text(metadata_path, json.dumps(payload, indent=2, sort_keys=True) + "\n")
        atomic_write_text(result_path, _patch_result_markdown(payload))
        return payload

    try:
        response_body: dict[str, Any] | None = None
        diff_text = ""
        summary = ""
        user_prompt = prompt
        for attempt in range(3):
            response_body = _chat_completion(
                provider=provider,
                model=profile.model,
                system_prompt=_patch_system_prompt(profile),
                user_prompt=user_prompt,
                api_key=api_key,
                timeout_seconds=_env_int("DEVFLOW_OPENROUTER_PATCH_TIMEOUT_SECONDS", PATCH_REQUEST_TIMEOUT_SECONDS),
                max_tokens=_env_int("DEVFLOW_OPENROUTER_PATCH_MAX_TOKENS", PATCH_MAX_TOKENS),
                reasoning=_patch_reasoning(prompt_mode),
            )
            content = _cap_text(_assistant_content(response_body), max_response_chars)
            raw_outputs.append(content)
            parsed = _json_object_from_text(content)
            status = str(parsed.get("status", "failed"))
            diff_text = normalize_hunk_line_counts(str(parsed.get("diff", "")))
            summary = str(parsed.get("summary") or parsed.get("reason") or "")
            if status != "ready":
                raise OpenRouterAgentError(summary or f"Patch proposer returned status '{status}'.")
            inspection = inspect_patch_proposal(diff_text)
            if inspection.structurally_valid:
                error = _patch_workspace_validation_error(root, task, diff_text)
                if error is None:
                    break
            else:
                error = inspection.parse_error or "Patch proposal is not structurally valid."
            if attempt == 2:
                raise OpenRouterAgentError(error)
            user_prompt = _patch_retry_prompt(prompt, error=error, previous_content=content)

        atomic_write_text(raw_output_path, _format_raw_outputs(raw_outputs))
        atomic_write_text(proposal_path, diff_text)
        payload = _patch_payload(
            root=root,
            status="success",
            run_id=run_id,
            task_id=task.id,
            task_title=task.title,
            profile=profile,
            provider=provider,
            prompt_mode=prompt_mode,
            prompt_chars=prompt_chars,
            prompt_truncated=truncated,
            raw_output_path=raw_output_path,
            proposal_path=proposal_path,
            metadata_path=metadata_path,
            result_path=result_path,
            summary=summary or "Patch proposal written.",
            error=None,
            usage=response_body.get("usage") if response_body and isinstance(response_body.get("usage"), dict) else None,
            will_call_provider=True,
        )
    except Exception as exc:
        if raw_outputs:
            atomic_write_text(raw_output_path, _format_raw_outputs(raw_outputs))
        error = _redact(str(exc), api_key=api_key)
        payload = _patch_payload(
            root=root,
            status="failed",
            run_id=run_id,
            task_id=task.id,
            task_title=task.title,
            profile=profile,
            provider=provider,
            prompt_mode=prompt_mode,
            prompt_chars=prompt_chars,
            prompt_truncated=truncated,
            raw_output_path=raw_output_path if raw_output_path.exists() else None,
            proposal_path=None,
            metadata_path=metadata_path,
            result_path=result_path,
            summary=error,
            error=error,
            usage=None,
            will_call_provider=True,
        )
    atomic_write_text(metadata_path, json.dumps(payload, indent=2, sort_keys=True) + "\n")
    atomic_write_text(result_path, _patch_result_markdown(payload))
    return payload


def _load_advisory_profile(root: Path, profile_id: str) -> tuple[AgentDefinition, ProviderDefinition]:
    profile, provider = _load_remote_profile(root, profile_id)
    if not is_remote_advisory_agent(profile, provider):
        raise OpenRouterAgentError(f"Profile '{profile_id}' is not approved for remote advisory runs.")
    return profile, provider


def _load_patch_profile(root: Path, profile_id: str) -> tuple[AgentDefinition, ProviderDefinition]:
    profile, provider = _load_remote_profile(root, profile_id)
    if not is_remote_patch_proposal_agent(profile, provider):
        raise OpenRouterAgentError(
            f"Profile '{profile_id}' is not approved for explicit remote patch proposals."
        )
    return profile, provider


def _load_remote_profile(root: Path, profile_id: str) -> tuple[AgentDefinition, ProviderDefinition]:
    try:
        profile = load_agent_registry(root).require_agent(profile_id)
        provider = load_provider_registry(root).require_provider(profile.provider)
    except (AgentRegistryError, KeyError) as exc:
        raise OpenRouterAgentError(str(exc)) from exc
    if provider.provider in {"ollama", "shell", "manual", "local"}:
        raise OpenRouterAgentError(f"Profile '{profile_id}' is not backed by a remote model provider.")
    if provider.adapter not in {"openai_compatible", "openai_chat", "anthropic_messages", "gemini"}:
        raise OpenRouterAgentError(
            f"Profile '{profile_id}' provider adapter '{provider.adapter}' is not supported by agent advise/propose-patch."
        )
    if not provider.enabled:
        raise OpenRouterAgentError(f"Provider '{provider.id}' is disabled.")
    return profile, provider


def _validate_advisory_job(job: str) -> None:
    if job not in ADVISORY_JOBS:
        allowed = ", ".join(sorted(ADVISORY_JOBS))
        raise OpenRouterAgentError(f"Unsupported advisory job '{job}'. Allowed: {allowed}.")


def _advisory_run_dir(root: Path, task_id: str | None, run_id: str) -> Path:
    if task_id:
        return root / ".devflow" / "tasks" / task_id / "agent-advisory-runs" / run_id
    return root / ".devflow" / "reports" / "agent-advisory-runs" / run_id


def _build_advisory_prompt(
    root: Path,
    profile: AgentDefinition,
    *,
    job: str,
    task_id: str | None,
    max_chars: int,
) -> tuple[str, bool]:
    lines = [
        "# Dev-Flow Remote Advisory Request",
        "",
        f"- Profile: {profile.id}",
        f"- Provider: {profile.provider}",
        f"- Model: {profile.model}",
        f"- Job: {job}",
        f"- Scope: {'task ' + task_id if task_id else 'repo'}",
        "",
        "## Hard Safety Contract",
        "- Advisory evidence only.",
        "- Do not create tasks, run workers, apply patches, run verification, promote, commit, or push.",
        "- Use only the bounded Dev-Flow evidence below; do not ask for or assume a full-repo scan.",
        "- Return one highest-impact next safe action.",
        "",
        "## Bounded Evidence",
    ]
    if task_id:
        packet = build_agent_packet(task_id, profile, root=root).model_dump(mode="json")
        lines.append(json.dumps(packet, indent=2, sort_keys=True))
    else:
        packet = build_supervisor_packet(root)
        lines.append(json.dumps(packet, indent=2, sort_keys=True))
    ledger = root / "docs" / "verification-ledger.md"
    if ledger.exists():
        lines.extend(["", "## Latest Verification Ledger Excerpt", ledger.read_text(encoding="utf-8")[:6000]])
    return _cap_prompt("\n".join(lines) + "\n", max_chars)


def _patch_prompt_mode() -> str:
    raw = os.environ.get(PATCH_PROMPT_MODE_ENV, "standard").strip().lower() or "standard"
    if raw not in PATCH_PROMPT_MODES:
        allowed = ", ".join(sorted(PATCH_PROMPT_MODES))
        raise OpenRouterAgentError(f"Invalid {PATCH_PROMPT_MODE_ENV}={raw!r}. Allowed values: {allowed}.")
    return raw


def _patch_reasoning(prompt_mode: str) -> dict[str, Any]:
    if prompt_mode == "minimal":
        # DeepSeek Flash can otherwise spend the whole small patch budget on hidden reasoning
        # and return content=null even though OpenRouter succeeded.
        return {"enabled": False, "exclude": True}
    return {
        "effort": os.environ.get("DEVFLOW_OPENROUTER_PATCH_REASONING_EFFORT", PATCH_REASONING_EFFORT),
        "exclude": True,
    }


def _build_patch_prompt(
    root: Path,
    profile: AgentDefinition,
    *,
    task: TaskRecord,
    prompt_mode: str,
    max_chars: int,
) -> tuple[str, bool]:
    if prompt_mode == "minimal":
        return _build_minimal_patch_prompt(root, profile, task=task, max_chars=max_chars)
    if prompt_mode != "standard":
        raise OpenRouterAgentError(f"Unsupported OpenRouter patch prompt mode: {prompt_mode}")

    packet = build_agent_packet(task.id, profile, root=root).model_dump(mode="json")
    context = _build_patch_context_excerpt(root, task.id)
    prompt = (
        "# Dev-Flow Explicit Patch Proposal Request\n\n"
        f"- Profile: {profile.id}\n"
        f"- Model: {profile.model}\n"
        f"- Task ID: {task.id}\n\n"
        "## Hard Safety Contract\n"
        "- Return a unified diff as proposal evidence only.\n"
        "- Do not claim the patch was applied, verified, promoted, committed, or pushed.\n"
        "- Dev-Flow review-patch, patch-dry-run, apply-patch, verification, and promotion gates remain required.\n\n"
        "## Bounded Worker Context Sources\n"
        f"{json.dumps(context, indent=2, sort_keys=True)}\n\n"
        "## Bounded Task Packet\n"
        f"{json.dumps(packet, indent=2, sort_keys=True)}\n"
    )
    return _cap_prompt(prompt, max_chars)


def _build_minimal_patch_prompt(
    root: Path,
    profile: AgentDefinition,
    *,
    task: TaskRecord,
    max_chars: int,
) -> tuple[str, bool]:
    from devflow.control_room.scout import RepoScout

    scout = RepoScout(root)
    description = scout.get_task_description(task.id)
    referenced_files = scout.get_referenced_files(task.title, description)
    snippets = _minimal_patch_snippets(root, task, referenced_files)
    verification_instruction = _minimal_verification_instruction(task, description)

    lines = [
        "# Dev-Flow Minimal Patch Proposal Request",
        "",
        f"- Profile: {profile.id}",
        f"- Model: {profile.model}",
        f"- Task ID: {task.id}",
        f"- Task title: {task.title}",
    ]
    if description:
        lines.append(f"- description: {description}")
    lines.extend(
        [
            "",
            "## Hard Safety Contract",
            "- Return a unified diff as proposal evidence only.",
            "- Do not claim the patch was applied, verified, promoted, committed, or pushed.",
            "- Dev-Flow review-patch, patch-dry-run, apply-patch, verification, and promotion gates remain required.",
            "- Use only the explicit task text and target snippets below.",
            "",
            "## Required JSON Schema",
            'Return only one JSON object: {"status": "ready|blocked|failed", "diff": "<unified diff>", "summary": "<short summary>"}.',
            '- Use status "ready" only when diff is a non-empty standard unified diff.',
            '- Use status "blocked" or "failed" with an empty diff when the requested patch cannot be proposed safely.',
            "",
            "## Target Snippets",
        ]
    )
    if snippets:
        for snippet in snippets:
            lines.extend(
                [
                    f"### {snippet['path']}",
                    f"- Source: {snippet['source']}",
                    f"- Included chars: {snippet['included_chars']}",
                    f"- Truncated: {str(snippet['truncated']).lower()}",
                    "```text",
                    str(snippet["content"]).rstrip(),
                    "```",
                    "",
                ]
            )
    else:
        lines.extend(["- No explicitly referenced existing files were found.", ""])

    if verification_instruction:
        lines.extend(["## Verification", f"- {verification_instruction}", ""])

    return _cap_prompt("\n".join(lines).rstrip() + "\n", max_chars)


def _minimal_patch_snippets(root: Path, task: TaskRecord, referenced_files: list[Path]) -> list[dict[str, Any]]:
    workspace_value = task.workspace_path or task.workspace
    workspace = absolute_path(root, workspace_value).resolve() if workspace_value else None
    snippets: list[dict[str, Any]] = []
    total_chars = 0

    for referenced_file in referenced_files:
        if len(snippets) >= MINIMAL_PATCH_SNIPPET_MAX_FILES:
            break
        try:
            relative = referenced_file.resolve().relative_to(root)
        except ValueError:
            continue

        workspace_candidate = workspace / relative if workspace else None
        source_path = workspace_candidate if workspace_candidate and workspace_candidate.is_file() else referenced_file
        if not source_path.exists() or not source_path.is_file():
            continue

        try:
            content = source_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            content = source_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        remaining = MINIMAL_PATCH_SNIPPET_MAX_CHARS_TOTAL - total_chars
        if remaining <= 0:
            break
        included = content[: min(MINIMAL_PATCH_SNIPPET_MAX_CHARS_PER_FILE, remaining)]
        total_chars += len(included)
        snippets.append(
            {
                "path": relative.as_posix(),
                "source": "task workspace" if workspace_candidate and source_path == workspace_candidate else "repo root",
                "content": included,
                "truncated": len(included) < len(content),
                "included_chars": len(included),
            }
        )

    return snippets


def _minimal_verification_instruction(task: TaskRecord, description: str) -> str | None:
    if task.verification_command and task.verification_command.strip():
        return f"Verification command: {task.verification_command.strip()}"

    task_text = f"{task.title}\n{description}"
    match = re.search(r"\bVerify with\s+([^\r\n]+)", task_text, re.IGNORECASE)
    if not match:
        return None
    command = match.group(1).strip().strip(".")
    if not command:
        return None
    return f"Verify with {command}"


def _build_patch_context_excerpt(root: Path, task_id: str) -> dict[str, Any]:
    try:
        from devflow.control_room.context_pack import build_context_pack

        pack_data = build_context_pack(root, task_id, "worker", persist_task_fit=False)
    except Exception as exc:
        return {"status": "unavailable", "error": str(exc), "included_sources": []}

    context_pack = pack_data.get("context_pack", {}) if isinstance(pack_data, dict) else {}
    sources_metadata = context_pack.get("sources_metadata") if isinstance(context_pack, dict) else []
    included_sources: list[dict[str, Any]] = []
    total_chars = 0
    max_total_chars = 120_000
    max_source_chars = 64_000

    if isinstance(sources_metadata, list):
        for source in sources_metadata:
            if not isinstance(source, dict) or source.get("mode") != "full":
                continue
            content = source.get("content")
            if not isinstance(content, str) or not content:
                continue
            remaining = max_total_chars - total_chars
            if remaining <= 0:
                break
            included = content[: min(max_source_chars, remaining)]
            total_chars += len(included)
            included_sources.append(
                {
                    "path": source.get("path"),
                    "authority": source.get("authority"),
                    "reason_included": source.get("reason_included"),
                    "content": included,
                    "truncated": len(included) < len(content),
                    "original_chars": len(content),
                    "included_chars": len(included),
                }
            )

    return {
        "status": "ready",
        "context_layer": context_pack.get("context_layer") if isinstance(context_pack, dict) else None,
        "estimated_tokens": context_pack.get("estimated_tokens") if isinstance(context_pack, dict) else None,
        "included_sources": included_sources,
        "included_source_count": len(included_sources),
        "included_chars": total_chars,
    }


def _advisory_system_prompt(profile: AgentDefinition, job: str) -> str:
    return (
        "You are a Dev-Flow advisory reviewer. Produce recommendation evidence only. "
        "Do not execute or claim mutations. Output JSON with keys: summary, recommendations, "
        "highest_impact_next_safe_action, risks. Each recommendation should include title, rationale, "
        "and next_safe_action. "
        f"Profile: {profile.id}. Job: {job}."
    )


def _patch_system_prompt(profile: AgentDefinition) -> str:
    return (
        "You are a Dev-Flow patch proposer. Output only JSON with keys: status, diff, summary. "
        "status must be ready, blocked, or failed. diff must be a standard unified diff when status is ready. "
        "Every hunk header line count must exactly match its body: context lines count as both old and new, "
        "minus lines count as old, and plus lines count as new. "
        "Do not include markdown fences. Do not claim application, verification, commit, push, or promotion. "
        f"Profile: {profile.id}."
    )


def _patch_retry_prompt(base_prompt: str, *, error: str, previous_content: str) -> str:
    retry_context = (
        "\n\n## Previous Patch Proposal Was Rejected\n"
        f"Validation error: {error}\n\n"
        "Return corrected JSON only, with a structurally valid unified diff. "
        "Do not change the requested scope. Recount every hunk header against the diff body before returning.\n\n"
        "Previous JSON content:\n"
        f"{_cap_text(previous_content, 64_000)}\n"
    )
    return _cap_prompt(base_prompt + retry_context, DEFAULT_AGENT_PROMPT_MAX_CHARS)[0]


def _patch_workspace_validation_error(root: Path, task: TaskRecord, diff_text: str) -> str | None:
    workspace_value = task.workspace_path or task.workspace
    if not workspace_value:
        return "Task workspace path is missing."
    workspace = absolute_path(root, workspace_value).resolve()
    if not workspace.exists() or not workspace.is_dir():
        return f"Task workspace is missing: {relative_path(root, workspace)}"
    try:
        patch_files = parse_unified_diff(diff_text)
        apply_patch_files(workspace, patch_files, dry_run=True)
    except (PatchParseError, PatchApplicationError, ValueError) as exc:
        return str(exc)
    return None


def _format_raw_outputs(raw_outputs: list[str]) -> str:
    if len(raw_outputs) == 1:
        content = raw_outputs[0]
        return content + ("\n" if content and not content.endswith("\n") else "")
    chunks: list[str] = []
    for index, content in enumerate(raw_outputs, start=1):
        chunks.extend([f"## Attempt {index}", "", content.rstrip(), ""])
    return "\n".join(chunks).rstrip() + "\n"


def _chat_completion(
    *,
    provider: ProviderDefinition,
    model: str,
    system_prompt: str,
    user_prompt: str,
    api_key: str | None,
    timeout_seconds: int | None = None,
    max_tokens: int | None = None,
    reasoning: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not provider.base_url:
        raise OpenRouterAgentError(f"Provider '{provider.id}' base_url is missing.")
    url, body, headers = _provider_request_parts(
        provider=provider,
        model=model,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        api_key=api_key,
        max_tokens=max_tokens,
        reasoning=reasoning,
    )
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    request_timeout = timeout_seconds or provider.default_timeout_seconds or 300
    try:
        with _total_deadline(request_timeout):
            with urllib.request.urlopen(request, timeout=request_timeout) as response:
                decoded = response.read().decode("utf-8")
    except TimeoutError as exc:
        raise OpenRouterAgentError(f"Provider '{provider.id}' request timed out after {request_timeout}s.") from exc
    except urllib.error.URLError as exc:
        raise OpenRouterAgentError(
            f"Provider '{provider.id}' request failed: {_redact(str(exc), api_key=api_key)}"
        ) from exc
    try:
        payload = json.loads(decoded)
    except json.JSONDecodeError as exc:
        raise OpenRouterAgentError(f"Provider '{provider.id}' returned invalid JSON: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise OpenRouterAgentError(f"Provider '{provider.id}' response root was not a JSON object.")
    return payload


def _provider_request_parts(
    *,
    provider: ProviderDefinition,
    model: str,
    system_prompt: str,
    user_prompt: str,
    api_key: str | None,
    max_tokens: int | None,
    reasoning: dict[str, Any] | None,
) -> tuple[str, dict[str, Any], dict[str, str]]:
    base_url = (provider.base_url or "").rstrip("/")
    if provider.adapter in {"openai_compatible", "openai_chat"}:
        url = f"{base_url}/chat/completions"
        body: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
        }
        if max_tokens is not None:
            body["max_tokens"] = max_tokens
        if reasoning is not None and provider.adapter == "openai_compatible":
            body["reasoning"] = reasoning
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        elif not is_local_openai_compatible_provider(provider):
            raise OpenRouterAgentError(f"Provider '{provider.id}' requires an API key but none was provided.")
        if provider.provider == "openrouter" or provider.id == "openrouter":
            headers["X-OpenRouter-Title"] = "DevFlow"
        return url, body, headers
    if provider.adapter == "anthropic_messages":
        url = f"{base_url}/v1/messages"
        body = {
            "model": model,
            "max_tokens": max_tokens or PATCH_MAX_TOKENS,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
            "temperature": 0.2,
        }
        return (
            url,
            body,
            {
                "Content-Type": "application/json",
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            },
        )
    if provider.adapter == "gemini":
        url = f"{base_url}/v1beta/models/{model}:generateContent"
        body = {
            "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "generationConfig": {
                "temperature": 0.2,
                "responseMimeType": "application/json",
            },
        }
        if max_tokens is not None:
            body["generationConfig"]["maxOutputTokens"] = max_tokens
        return (
            url,
            body,
            {
                "Content-Type": "application/json",
                "x-goog-api-key": api_key,
            },
        )
    raise OpenRouterAgentError(f"Provider adapter '{provider.adapter}' is not supported.")


@contextmanager
def _total_deadline(seconds: int):
    if seconds <= 0 or threading.current_thread() is not threading.main_thread() or not hasattr(signal, "SIGALRM"):
        yield
        return

    def raise_timeout(signum: int, frame: object) -> None:
        raise TimeoutError

    previous_handler = signal.getsignal(signal.SIGALRM)
    signal.signal(signal.SIGALRM, raise_timeout)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def _default_api_key_env(provider: ProviderDefinition) -> str:
    if provider.provider == "openrouter" or provider.id == "openrouter":
        return "OPENROUTER_API_KEY"
    if provider.adapter == "anthropic_messages":
        return "ANTHROPIC_API_KEY"
    if provider.adapter == "gemini":
        return "GEMINI_API_KEY"
    if provider.adapter == "openai_chat":
        return "OPENAI_API_KEY"
    return f"{provider.id.upper()}_API_KEY"


def _assistant_content(response_body: dict[str, Any]) -> str:
    choices = response_body.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, dict):
            message = first.get("message")
            if isinstance(message, dict):
                content = message.get("content")
                if isinstance(content, str):
                    return content.strip()
            text = first.get("text")
            if isinstance(text, str):
                return text.strip()
    content = response_body.get("content")
    if isinstance(content, list) and content:
        chunks: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text" and isinstance(item.get("text"), str):
                chunks.append(item["text"])
        if chunks:
            return "\n".join(chunks).strip()
    candidates = response_body.get("candidates")
    if isinstance(candidates, list) and candidates:
        parts = candidates[0].get("content", {}).get("parts", []) if isinstance(candidates[0], dict) else []
        chunks = [part.get("text", "") for part in parts if isinstance(part, dict) and isinstance(part.get("text"), str)]
        if chunks:
            return "\n".join(chunks).strip()
    raise OpenRouterAgentError("Provider response did not include assistant content.")


def _extract_recommendations(content: str) -> list[dict[str, str]]:
    try:
        parsed = _json_object_from_text(content)
    except OpenRouterAgentError:
        return [{"title": "Review advisory response", "rationale": content[:500], "next_safe_action": "human review"}]
    raw_recommendations = parsed.get("recommendations")
    recommendations: list[dict[str, str]] = []
    if isinstance(raw_recommendations, list):
        for item in raw_recommendations[:8]:
            if not isinstance(item, dict):
                continue
            recommendations.append(
                {
                    "title": str(item.get("title") or item.get("action") or "Recommendation"),
                    "rationale": str(item.get("rationale") or item.get("reason") or ""),
                    "next_safe_action": str(
                        item.get("next_safe_action") or item.get("command") or item.get("action") or "human review"
                    ),
                }
            )
    if not recommendations:
        next_action = str(parsed.get("highest_impact_next_safe_action") or "human review")
        recommendations.append(
            {
                "title": "Highest-impact next safe action",
                "rationale": str(parsed.get("summary") or ""),
                "next_safe_action": next_action,
            }
        )
    return recommendations


def _json_object_from_text(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.startswith("json"):
            stripped = stripped[4:].strip()
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise OpenRouterAgentError(f"Expected JSON object content: {exc.msg}") from exc
    if not isinstance(parsed, dict):
        raise OpenRouterAgentError("Expected JSON object content.")
    return parsed


def _advice_payload(
    *,
    root: Path,
    status: str,
    run_id: str,
    task_id: str | None,
    profile: AgentDefinition,
    provider: ProviderDefinition,
    job: str,
    prompt_path: Path,
    response_path: Path | None,
    raw_response_path: Path | None,
    metadata_path: Path,
    prompt_truncated: bool,
    usage: dict[str, Any] | None,
    recommendations: list[dict[str, str]],
    error: str | None,
    will_call_provider: bool,
    local_model_server_lifecycle: dict[str, Any] | None = None,
) -> dict[str, Any]:
    evidence_dir = metadata_path.parent
    payload = {
        "schema_version": 1,
        "dry_run": False,
        "status": status,
        "run_id": run_id,
        "task_id": task_id,
        "profile_id": profile.id,
        "job": job,
        "provider": profile.provider,
        "model": profile.model,
        "adapter": profile.adapter,
        "provider_base_url": provider.base_url,
        "evidence_dir": relative_path(root, evidence_dir),
        "prompt_path": relative_path(root, prompt_path),
        "response_path": relative_path(root, response_path) if response_path else None,
        "raw_response_path": relative_path(root, raw_response_path) if raw_response_path else None,
        "run_metadata_path": relative_path(root, metadata_path),
        "prompt_truncated": prompt_truncated,
        "usage": usage,
        "recommendations": recommendations,
        "will_call_provider": will_call_provider,
        "local_model_server_lifecycle": local_model_server_lifecycle,
        "safety_flags": _safety_flags(),
    }
    if error:
        payload["error"] = error
    return payload


def _patch_payload(
    *,
    root: Path,
    status: str,
    run_id: str,
    task_id: str,
    task_title: str,
    profile: AgentDefinition,
    provider: ProviderDefinition,
    prompt_mode: str,
    prompt_chars: int,
    prompt_truncated: bool,
    raw_output_path: Path | None,
    proposal_path: Path | None,
    metadata_path: Path,
    result_path: Path,
    summary: str,
    error: str | None,
    usage: dict[str, Any] | None,
    will_call_provider: bool,
) -> dict[str, Any]:
    payload = {
        "schema_version": 1,
        "status": status,
        "run_id": run_id,
        "task_id": task_id,
        "task_title": task_title,
        "profile_id": profile.id,
        "provider": profile.provider,
        "model": profile.model,
        "adapter": profile.adapter,
        "provider_base_url": provider.base_url,
        "prompt_mode": prompt_mode,
        "prompt_chars": prompt_chars,
        "raw_output_path": relative_path(root, raw_output_path) if raw_output_path else None,
        "proposal_patch_path": relative_path(root, proposal_path) if proposal_path else None,
        "run_metadata_path": relative_path(root, metadata_path),
        "result_path": relative_path(root, result_path),
        "summary": summary,
        "prompt_truncated": prompt_truncated,
        "usage": usage,
        "will_call_provider": will_call_provider,
        "safety_flags": _safety_flags(),
        "next_safe_action": f"devflow task review-patch {task_id} --agent {profile.id}",
    }
    if error:
        payload["error"] = error
    return payload


def _patch_result_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# OpenRouter Patch Proposal Evidence",
        "",
        f"Status: {payload['status']}",
        f"Task: {payload['task_id']}",
        f"Profile: {payload['profile_id']}",
        f"Prompt mode: {payload.get('prompt_mode', 'standard')}",
        f"Summary: {payload['summary']}",
        "",
        "Next safe action:",
        payload["next_safe_action"],
        "",
        "Safety:",
        "- Proposal evidence only.",
        "- Review, dry-run, apply, verification, and promotion gates remain required.",
    ]
    return "\n".join(lines) + "\n"


def _safety_flags() -> dict[str, bool]:
    return {
        "will_create_tasks": False,
        "will_run_workers": False,
        "will_apply_patch": False,
        "will_verify": False,
        "will_promote": False,
        "will_commit": False,
        "will_push": False,
        "will_write_source": False,
    }


def _cap_prompt(prompt: str, max_chars: int) -> tuple[str, bool]:
    if max_chars < 1:
        max_chars = DEFAULT_AGENT_PROMPT_MAX_CHARS
    if len(prompt) <= max_chars:
        return prompt, False
    suffix = f"\n\n[prompt capped at {max_chars} characters]\n"
    keep = max(0, max_chars - len(suffix))
    return prompt[:keep] + suffix, True


def _cap_text(text: str, max_chars: int) -> str:
    if max_chars < 1 or len(text) <= max_chars:
        return text
    suffix = f"\n\n[response capped at {max_chars} characters]\n"
    keep = max(0, max_chars - len(suffix))
    return text[:keep] + suffix


def _safe_json(payload: dict[str, Any], *, api_key: str | None = None) -> str:
    return _redact(json.dumps(payload, indent=2, sort_keys=True) + "\n", api_key=api_key)


def _redact(text: str, *, api_key: str | None = None) -> str:
    redacted = text
    if api_key:
        redacted = redacted.replace(api_key, "[redacted]")
    return SECRET_PATTERN.sub("[redacted]", redacted)


def _new_run_id(profile_id: str) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"{timestamp}-{os.urandom(4).hex()}-{profile_id}"
