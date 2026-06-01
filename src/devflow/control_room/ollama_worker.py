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

        run_meta: dict[str, Any] = {
            "task_id": worker_input.task_id,
            "agent_id": evidence_agent_id,
            "adapter": self.name,
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
                    "finished_at": finished_at,
                    "model": model,
                    "provider": provider_id,
                    "base_url": base_url,
                    "timeout_seconds": timeout,
                    "raw_output_path": str(raw_output_path),
                    "proposal_patch_path": str(patch_file) if patch_file.exists() else None,
                }
            )
            if response is not None:
                run_meta["response"] = response
            atomic_write_text(run_json_path, json.dumps(run_meta, indent=2, sort_keys=True) + "\n")
            _write_result(result_file, worker_input.task_id, evidence_agent_id, status, summary, response)
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
            "5. Set status to blocked with a clear reason if the task cannot be completed safely."
        )

        prompt = _build_prompt(
            worker_input=worker_input,
            agent_id=evidence_agent_id,
            task_path=task_path,
            agent_dir=agent_dir,
            context_pack=context_pack,
        )

        url = f"{base_url.rstrip('/')}/api/generate"
        data = {
            "model": model,
            "prompt": prompt,
            "system": system_instruction,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.2},
        }

        with worker_input.log_file.open("a", encoding="utf-8") as log:
            log.write(f"Connecting to local Ollama on {url} (model: {model}, timeout: {timeout}s)...\n")

        req = urllib.request.Request(
            url,
            data=json.dumps(data).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                res_body = json.loads(response.read().decode("utf-8"))
                response_text = str(res_body.get("response", ""))
                run_meta["ollama_response"] = {k: v for k, v in res_body.items() if k != "response"}
        except urllib.error.URLError as exc:
            message = f"Error connecting to local Ollama agent: {exc}"
            with worker_input.log_file.open("a", encoding="utf-8") as log:
                log.write(f"{message}\n")
            return finish(status="worker_failed", summary=message, exit_code=1)
        except Exception as exc:
            message = f"Ollama execution encountered an exception: {exc}"
            with worker_input.log_file.open("a", encoding="utf-8") as log:
                log.write(f"{message}\n")
            return finish(status="worker_failed", summary=message, exit_code=1)

        atomic_write_text(raw_output_path, response_text)

        try:
            diff_data = repair_and_parse_json(response_text)
        except Exception as exc:
            message = f"JSON parsing of agent response failed: {exc}"
            with worker_input.log_file.open("a", encoding="utf-8") as log:
                log.write(f"{message}\n")
                log.write(f"Raw response preserved at {raw_output_path}\n")
            return finish(status="worker_failed", summary=message, exit_code=1)

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
            message = "Worker returned status ready but did not include a non-empty unified diff."
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

    for item in context_pack.get("sources_metadata", []):
        if item.get("mode") == "full":
            prompt_lines.append(f"--- File: {item['path']} ---")
            prompt_lines.append(str(item.get("content", "")))
            prompt_lines.append("")

    prompt_lines.extend(
        [
            "",
            "Return only the required JSON. The diff must target paths relative to the workspace.",
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


def _write_result(
    result_file: Path,
    task_id: str,
    agent_id: str,
    status: str,
    summary: str,
    response: dict[str, Any] | None,
) -> None:
    response_lines = ""
    if response:
        response_lines = "\n## Response Summary\n\n```json\n" + json.dumps(response, indent=2, sort_keys=True) + "\n```\n"
    body = (
        f"# Ollama Worker Result: {task_id}\n\n"
        f"Agent: {agent_id}\n\n"
        f"Status: {status}\n\n"
        f"Summary: {summary}\n"
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
