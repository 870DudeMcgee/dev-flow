from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from devflow.control_room.agent_registry import (
    is_local_patch_runtime_agent,
    load_agent_registry,
    load_provider_registry,
)
from devflow.control_room.context_pack import build_context_pack
from devflow.control_room.json_utils import repair_and_parse_json
from devflow.control_room.log_sanitizer import latest_visible_log_line
from devflow.control_room.models import WorkerInput, WorkerResult
from devflow.control_room.ollama_generation import (
    OllamaPatchGenerationSettings,
    build_ollama_patch_request_payload,
    settings_for_ollama_patch_agent,
)
from devflow.control_room.persistence import atomic_write_text


class OllamaChatWorkerAdapter:
    name = "ollama_chat"

    def run(self, worker_input: WorkerInput) -> WorkerResult:
        worker_input.workspace_path.mkdir(parents=True, exist_ok=True)
        worker_input.log_file.parent.mkdir(parents=True, exist_ok=True)

        started_at = _utc_now()
        task_path = worker_input.repo_root / ".devflow" / "tasks" / worker_input.task_id
        env_agent_id = worker_input.env.get("DEVFLOW_AGENT_ID")
        evidence_agent_id = env_agent_id or "default_agent"
        agent_dir = task_path / "agents" / evidence_agent_id
        agent_dir.mkdir(parents=True, exist_ok=True)
        (agent_dir / "logs").mkdir(parents=True, exist_ok=True)

        raw_output_path = agent_dir / "raw_output.md"
        patch_file = agent_dir / "proposal.patch"
        run_json_path = agent_dir / "run.json"
        result_file = worker_input.result_file if env_agent_id else agent_dir / "result.md"
        atomic_write_text(raw_output_path, "")

        model = "qwen2.5-coder:14b"
        base_url = "http://127.0.0.1:11434"
        timeout = worker_input.timeout_seconds or 300
        provider_id = "ollama"
        selected_agent = None
        generation_settings = OllamaPatchGenerationSettings(endpoint="generate")

        run_meta: dict[str, Any] = {
            "task_id": worker_input.task_id,
            "agent_id": evidence_agent_id,
            "adapter": self.name,
            "worker_runtime_id": self.name,
            "started_at": started_at,
            "workspace": str(worker_input.workspace_path),
            "status": "running",
        }

        def finish(
            *,
            status: str,
            summary: str,
            exit_code: int,
            response: dict[str, Any] | None = None,
        ) -> WorkerResult:
            finished_at = _utc_now()
            run_meta.update(
                {
                    "status": status,
                    "summary": summary,
                    "exit_code": exit_code,
                    "error": summary if status in {"worker_failed", "blocked"} else None,
                    "failure_reason": summary if status in {"worker_failed", "blocked"} else None,
                    "finished_at": finished_at,
                    "model": model,
                    "provider": provider_id,
                    "base_url": base_url,
                    "timeout_seconds": timeout,
                    "raw_output_captured": raw_output_path.exists() and raw_output_path.stat().st_size > 0,
                    "raw_output_path": str(raw_output_path),
                    "proposal_patch_found": patch_file.exists() and patch_file.stat().st_size > 0,
                    "proposal_patch_path": str(patch_file) if patch_file.exists() else None,
                    "proposal_patch_byte_length": patch_file.stat().st_size if patch_file.exists() else 0,
                    "proposed_file_count": len(_proposed_file_paths(patch_file.read_text(encoding="utf-8"))) if patch_file.exists() else 0,
                    "proposed_file_paths": _proposed_file_paths(patch_file.read_text(encoding="utf-8")) if patch_file.exists() else [],
                    "next_suggested_command": _next_suggested_command(worker_input.task_id, evidence_agent_id, status, patch_file),
                }
            )
            if response is not None:
                run_meta["response"] = response
            atomic_write_text(run_json_path, json.dumps(run_meta, indent=2, sort_keys=True) + "\n")
            _write_result(
                result_file,
                worker_input.task_id,
                evidence_agent_id,
                status,
                summary,
                response,
                raw_output_path=raw_output_path,
                patch_file=patch_file,
            )
            if status == "worker_failed":
                _write_worker_failed(agent_dir, worker_input.task_id, evidence_agent_id, summary)
            elif status == "blocked":
                _append_blocked_question(agent_dir, worker_input.task_id, evidence_agent_id, summary)
            return WorkerResult(
                status=status,  # type: ignore[arg-type]
                summary=summary,
                exit_code=exit_code,
                latest_log_line=latest_visible_log_line(worker_input.log_file),
                result_file=result_file,
                log_file=worker_input.log_file,
            )

        with worker_input.log_file.open("w", encoding="utf-8") as log:
            log.write(f"=== Ollama Worker Execution for Task {worker_input.task_id} ===\n")
            log.flush()

        if env_agent_id:
            try:
                registry = load_agent_registry(worker_input.repo_root)
                agent = registry.require_agent(env_agent_id)
                providers = load_provider_registry(worker_input.repo_root)
                provider_def = providers.require_provider(agent.provider)
                if not is_local_patch_runtime_agent(agent, provider=provider_def):
                    return finish(
                        status="worker_failed",
                        summary=f"Agent '{env_agent_id}' is not approved for local Ollama patch runtime.",
                        exit_code=1,
                    )
                selected_agent = agent
                model = agent.model
                provider_id = provider_def.provider
                if provider_def.base_url:
                    base_url = provider_def.base_url
                if provider_def.default_timeout_seconds:
                    timeout = provider_def.default_timeout_seconds
            except Exception as exc:
                with worker_input.log_file.open("a", encoding="utf-8") as log:
                    log.write(f"Failed resolving Ollama agent/provider registry: {exc}\n")
                return finish(
                    status="worker_failed",
                    summary=f"Failed resolving Ollama agent/provider registry: {exc}",
                    exit_code=1,
                )

        try:
            pack_data = build_context_pack(worker_input.repo_root, worker_input.task_id, "worker")
            context_pack = pack_data.get("context_pack", {})
        except Exception as exc:
            context_pack = {}
            with worker_input.log_file.open("a", encoding="utf-8") as log:
                log.write(f"Warning generating context pack: {exc}\n")

        system_instruction = (
            "You are a software engineer working inside a Dev-Flow isolated workspace. "
            "You may propose code changes only as a unified diff. Dev-Flow, not you, applies "
            "patches, runs verification, and controls promotion.\n\n"
            "Output only raw JSON matching this schema, with no markdown or extra text:\n"
            "{\n"
            "  \"status\": \"ready\" | \"blocked\" | \"failed\",\n"
            "  \"diff\": \"string (unified diff format)\",\n"
            "  \"touched_paths\": [\"string\"],\n"
            "  \"risk\": \"low\" | \"medium\" | \"high\" | \"critical\",\n"
            "  \"confidence\": 0.0\n"
            "}\n\n"
            "Diff requirements:\n"
            "1. Use standard git unified diff format.\n"
            "2. Context lines must match the target files exactly.\n"
            "3. Header paths must be relative workspace paths, e.g. --- a/src/foo.py and +++ b/src/foo.py.\n"
            "4. Do not include binary diffs, renames, mode changes, or truncated chunks.\n"
            "5. Do not modify files outside the task boundary.\n"
            "6. Do not claim success unless a real unified diff is present in the diff field.\n"
            "7. Dev-Flow applies, verifies, and promotes separately; you only propose the patch.\n"
            "8. Set status to blocked with a clear reason if the task cannot be completed safely."
        )

        prompt = _build_prompt(
            worker_input=worker_input,
            agent_id=evidence_agent_id,
            task_path=task_path,
            agent_dir=agent_dir,
            context_pack=context_pack,
        )

        generation_settings = settings_for_ollama_patch_agent(
            evidence_agent_id,
            model,
            selected_agent,
        )
        url = f"{base_url.rstrip('/')}{generation_settings.endpoint_path}"
        data = build_ollama_patch_request_payload(
            model=model,
            system_instruction=system_instruction,
            prompt=prompt,
            settings=generation_settings,
        )
        run_meta.update(
            {
                "request_endpoint": generation_settings.endpoint_path,
                "request_payload_shape": generation_settings.payload_shape,
                "request_options": generation_settings.options(),
                "request_format": "json" if generation_settings.format_json else None,
                "native_chat_think": generation_settings.think if generation_settings.endpoint == "chat" else None,
                "prompt_chars": len(prompt),
                "system_instruction_chars": len(system_instruction),
            }
        )

        with worker_input.log_file.open("a", encoding="utf-8") as log:
            log.write(
                "Connecting to local Ollama on "
                f"{url} (model: {model}, timeout: {timeout}s, "
                f"num_ctx: {generation_settings.num_ctx}, "
                f"num_predict: {generation_settings.num_predict})...\n"
            )

        req = urllib.request.Request(
            url,
            data=json.dumps(data).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                res_body = json.loads(response.read().decode("utf-8"))
                run_meta["ollama_response"] = _ollama_response_metadata(res_body)
        except urllib.error.HTTPError as exc:
            raw_error = _http_error_detail(exc)
            if _looks_like_missing_model(raw_error, model, exc.code):
                message = (
                    f"Ollama model '{model}' is missing at configured local URL {base_url}. "
                    f"Raw Ollama error: {raw_error}. "
                    f"Suggested next action: run 'ollama pull {model}' or correct the model name "
                    "in the registry/provider configuration."
                )
            else:
                message = (
                    f"Ollama HTTP request failed at configured local URL {base_url}. "
                    f"Raw Ollama error: {raw_error}."
                )
            with worker_input.log_file.open("a", encoding="utf-8") as log:
                log.write(f"{message}\n")
            return finish(status="worker_failed", summary=message, exit_code=1)
        except urllib.error.URLError as exc:
            message = (
                f"Ollama could not be reached at configured local URL {base_url}. "
                f"Raw error: {exc}. "
                "Suggested next action: start Ollama with 'ollama serve' or the Ollama app, then retry."
            )
            with worker_input.log_file.open("a", encoding="utf-8") as log:
                log.write(f"{message}\n")
            return finish(status="worker_failed", summary=message, exit_code=1)
        except Exception as exc:
            message = f"Ollama execution encountered an exception: {exc}"
            with worker_input.log_file.open("a", encoding="utf-8") as log:
                log.write(f"{message}\n")
            return finish(status="worker_failed", summary=message, exit_code=1)

        # Extract/parse model proposal JSON from the Ollama response
        diff_data = None
        extracted_text = None
        parse_error = None

        # Try message.content, response, content, thinking in order
        candidates = []
        failed_candidate_text = None
        
        # 1. message.content
        msg = res_body.get("message")
        if isinstance(msg, dict):
            candidates.append(("message.content", msg.get("content")))
        if "message.content" in res_body:
            candidates.append(("message.content", res_body.get("message.content")))
            
        # 2. response
        candidates.append(("response", res_body.get("response")))
        
        # 3. content
        candidates.append(("content", res_body.get("content")))
        
        # 4. thinking
        candidates.append(("thinking", res_body.get("thinking")))

        for loc_name, val in candidates:
            if val is None:
                continue
            
            if isinstance(val, (dict, list)):
                if isinstance(val, list):
                    diff_data = val
                    extracted_text = json.dumps(val, indent=2)
                    parse_error = ValueError("Expected a JSON object (dict), but got a list.")
                    break
                else:
                    diff_data = val
                    extracted_text = json.dumps(val, indent=2)
                    break
            elif isinstance(val, str):
                try:
                    diff_data = repair_and_parse_json(val)
                    extracted_text = val
                    break
                except Exception as e:
                    if failed_candidate_text is None:
                        failed_candidate_text = val
                    if parse_error is None:
                        parse_error = e
            else:
                try:
                    str_val = str(val)
                    diff_data = repair_and_parse_json(str_val)
                    extracted_text = str_val
                    break
                except Exception as e:
                    if failed_candidate_text is None:
                        failed_candidate_text = str_val
                    if parse_error is None:
                        parse_error = e

        if diff_data is None or isinstance(diff_data, list):
            if diff_data is not None:
                response_text = extracted_text
            else:
                response_text = (
                    extracted_text
                    if extracted_text is not None
                    else failed_candidate_text
                    if failed_candidate_text is not None
                    else str(res_body.get("response", ""))
                )
                extracted_text = response_text
                
            if parse_error is None:
                if isinstance(diff_data, list):
                    parse_error = ValueError("Expected a JSON object (dict), but got a list.")
                else:
                    parse_error = ValueError("No JSON object or array start found in text")
            
            atomic_write_text(raw_output_path, extracted_text)
            response_meta = _ollama_response_metadata(res_body)
            message = _malformed_json_message(raw_output_path, parse_error, response_meta)
            with worker_input.log_file.open("a", encoding="utf-8") as log:
                log.write(f"{message}\n")
                log.write(f"Raw response preserved at {raw_output_path}\n")
            return finish(status="worker_failed", summary=message, exit_code=1)

        atomic_write_text(raw_output_path, extracted_text)

        response_summary = _response_summary(diff_data)
        response_status = str(diff_data.get("status", "failed"))
        if response_status != "ready":
            reason = str(
                diff_data.get("blocked_reason")
                or diff_data.get("reason")
                or "Worker indicated blocked/failed state"
            )
            with worker_input.log_file.open("a", encoding="utf-8") as log:
                log.write(f"Worker did not produce a ready patch. Status: {response_status}. Reason: {reason}\n")
            return finish(
                status="blocked" if response_status == "blocked" else "worker_failed",
                summary=reason,
                exit_code=1,
                response=response_summary,
            )

        diff_text = str(diff_data.get("diff", ""))
        if not diff_text.strip():
            message = f"Worker returned status ready but did not include a non-empty unified diff; inspect raw output at {raw_output_path}."
            with worker_input.log_file.open("a", encoding="utf-8") as log:
                log.write(f"{message}\n")
            return finish(status="worker_failed", summary=message, exit_code=1, response=response_summary)

        atomic_write_text(patch_file, diff_text)

        with worker_input.log_file.open("a", encoding="utf-8") as log:
            log.write(f"Raw output written to {raw_output_path}\n")
            log.write(f"Proposed patch written to {patch_file}\n")
            log.write("Worker completed successfully.\n")

        summary = "Worker completed successfully and wrote proposal.patch"
        return finish(status="complete", summary=summary, exit_code=0, response=response_summary)


def _build_prompt(
    *,
    worker_input: WorkerInput,
    agent_id: str,
    task_path: Path,
    agent_dir: Path,
    context_pack: dict[str, Any],
) -> str:
    prompt_lines = [
        f"TASK ID: {worker_input.task_id}",
        f"AGENT ID: {agent_id}",
        f"WORKSPACE: {worker_input.workspace_path}",
        "",
        "DEV-FLOW TASK PACKET:",
        _read_first_existing(agent_dir / "packet.json", task_path / "packet.json", worker_input.task_file),
        "",
        "CONTEXT SOURCES:",
    ]

    has_sources = False
    for item in context_pack.get("sources_metadata", []):
        if item.get("mode") == "full":
            prompt_lines.append(f"--- File: {item['path']} ---")
            prompt_lines.append(str(item.get("content", "")))
            prompt_lines.append("")
            has_sources = True

    if not has_sources:
        prompt_lines.append("No relevant file excerpt is available. Do not invent file content or assume specific existing content unless you are absolutely sure or creating a new file.")

    prompt_lines.extend(
        [
            "",
            "REQUIRED OUTPUT FORMAT:",
            "Return only the required JSON object. Do not include prose outside the JSON.",
            "The diff field must contain a unified diff only and target paths relative to the workspace.",
            "Do not read stale patch dry-run artifacts, unrelated logs, prior raw outputs, archive material, caches, virtualenvs, binaries, .git, or _legacy unless the task explicitly targets them.",
        ]
    )
    return "\n".join(prompt_lines)


def _read_first_existing(*paths: Path) -> str:
    for path in paths:
        if path.exists():
            return path.read_text(encoding="utf-8")
    return "{}"


def _response_summary(diff_data: dict[str, Any]) -> dict[str, Any]:
    touched_paths = diff_data.get("touched_paths")
    if not isinstance(touched_paths, list):
        touched_paths = []
    return {
        "status": diff_data.get("status"),
        "touched_paths": touched_paths,
        "risk": diff_data.get("risk"),
        "confidence": diff_data.get("confidence"),
    }


def _ollama_response_metadata(res_body: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in res_body.items() if k not in {"response", "message"}}


def _malformed_json_message(raw_output_path: Path, parse_error: Exception, response_meta: dict[str, Any]) -> str:
    base = f"Malformed JSON from local Ollama worker; inspect raw output at {raw_output_path}. Parser error: {parse_error}"
    done_reason = response_meta.get("done_reason")
    eval_count = response_meta.get("eval_count")
    prompt_eval_count = response_meta.get("prompt_eval_count")
    if done_reason == "length":
        detail = (
            "Ollama stopped at length before returning complete JSON "
            f"(prompt_eval_count={prompt_eval_count}, eval_count={eval_count})."
        )
        if isinstance(eval_count, int) and eval_count <= 1:
            detail += " The model emitted only the JSON prefix or an equivalent one-token response."
        return f"{base}. {detail}"
    return base


def _proposed_file_paths(diff_text: str) -> list[str]:
    paths: list[str] = []
    for line in diff_text.splitlines():
        if not line.startswith("diff --git "):
            continue
        parts = line.split()
        if len(parts) < 4:
            continue
        for raw in parts[2:4]:
            path = raw[2:] if raw.startswith(("a/", "b/")) else raw
            if path != "/dev/null" and path not in paths:
                paths.append(path)
    return paths


def _next_suggested_command(task_id: str, agent_id: str, status: str, patch_file: Path) -> str:
    if status == "complete" and patch_file.exists() and patch_file.stat().st_size > 0:
        return f"devflow task review-patch {task_id} --agent {agent_id}"
    if status in {"worker_failed", "blocked"}:
        return f"devflow task escalation-packet {task_id} --agent {agent_id}"
    return f"devflow task show {task_id}"


def _write_result(
    result_file: Path,
    task_id: str,
    agent_id: str,
    status: str,
    summary: str,
    response: dict[str, Any] | None,
    *,
    raw_output_path: Path,
    patch_file: Path,
) -> None:
    proposed_paths = _proposed_file_paths(patch_file.read_text(encoding="utf-8")) if patch_file.exists() else []
    patch_bytes = patch_file.stat().st_size if patch_file.exists() else 0
    response_lines = ""
    if response:
        response_lines = "\n## Response Summary\n\n```json\n" + json.dumps(response, indent=2, sort_keys=True) + "\n```\n"
    next_action = _next_suggested_command(task_id, agent_id, status, patch_file)
    body = (
        f"# Ollama Worker Result: {task_id}\n\n"
        f"Agent: {agent_id}\n\n"
        f"Status: {status}\n\n"
        f"Summary: {summary}\n\n"
        "## Run Evidence\n\n"
        f"- Qwopus/local Ollama ran: {'yes' if status else 'unknown'}\n"
        f"- Raw output captured: {'yes' if raw_output_path.exists() and raw_output_path.stat().st_size > 0 else 'no'}\n"
        f"- Raw output path: {raw_output_path.name}\n"
        f"- Proposal patch detected: {'yes' if patch_bytes > 0 else 'no'}\n"
        f"- Proposal patch path: {patch_file.name if patch_file.exists() else 'none'}\n"
        f"- Proposal patch bytes: {patch_bytes}\n"
        f"- Proposed files: {', '.join(proposed_paths) if proposed_paths else 'none'}\n"
        f"- Next action: `{next_action}`\n"
        f"{response_lines}"
    )
    atomic_write_text(result_file, body)


def _write_worker_failed(agent_dir: Path, task_id: str, agent_id: str, summary: str) -> None:
    payload = {
        "status": "worker_failed",
        "task_id": task_id,
        "agent_id": agent_id,
        "summary": summary,
        "error_type": "ollama_chat_worker_failed",
        "evidence": {
            "raw_output": "raw_output.md",
            "run": "run.json",
            "log": "logs/worker.log",
        },
        "next_safe_action": "Inspect raw_output.md and worker.log, adjust the task or retry the local Ollama run.",
    }
    atomic_write_text(agent_dir / "worker_failed.json", json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _append_blocked_question(agent_dir: Path, task_id: str, agent_id: str, question: str) -> None:
    payload = {
        "type": "blocked_question",
        "task_id": task_id,
        "agent_id": agent_id,
        "question": question,
        "created_at": _utc_now(),
    }
    with (agent_dir / "questions.jsonl").open("a", encoding="utf-8") as questions:
        questions.write(json.dumps(payload, sort_keys=True) + "\n")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _http_error_detail(exc: urllib.error.HTTPError) -> str:
    try:
        body = exc.read().decode("utf-8", errors="replace")
    except Exception:
        body = ""
    prefix = f"HTTP {exc.code} {exc.reason}".strip()
    return f"{prefix}: {body}" if body else prefix


def _looks_like_missing_model(raw_error: str, model: str, status_code: int) -> bool:
    lowered = raw_error.lower()
    return (
        status_code == 404
        or model.lower() in lowered and ("not found" in lowered or "pull" in lowered or "missing" in lowered)
        or "model" in lowered and ("not found" in lowered or "pull" in lowered)
    )
