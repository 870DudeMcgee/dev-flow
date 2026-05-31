from __future__ import annotations

import sys
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from devflow.control_room.log_sanitizer import latest_visible_log_line
from devflow.control_room.models import WorkerInput, WorkerResult
from devflow.control_room.paths import relative_path


@dataclass(frozen=True)
class ManualAgentEvidence:
    state: str
    handoff_path: str | None = None
    result_path: str | None = None
    question_path: str | None = None
    failure_path: str | None = None
    summary: str | None = None
    question: str | None = None
    failure: str | None = None


class ManualWorkerAdapter:
    name = "manual"

    def run(self, worker_input: WorkerInput) -> WorkerResult:
        worker_input.workspace_path.mkdir(parents=True, exist_ok=True)
        worker_input.log_file.parent.mkdir(parents=True, exist_ok=True)
        agent_id = worker_input.env.get("DEVFLOW_AGENT_ID")
        handoff_path = None
        if agent_id:
            handoff_path = worker_input.result_file.parent / "handoff.md"
            handoff_path.write_text(_build_handoff(worker_input, agent_id), encoding="utf-8")

        # Write orienting manual instructions log
        with worker_input.log_file.open("w", encoding="utf-8") as log:
            log.write(f"=== Manual Worker Escalation for Task {worker_input.task_id} ===\n")
            log.write(f"Workspace Path: {worker_input.workspace_path.resolve()}\n")
            if agent_id:
                log.write(f"Agent ID: {agent_id}\n")
            if handoff_path is not None:
                log.write(f"Manual handoff: {handoff_path}\n")
            log.write(f"Command provided: {' '.join(worker_input.command) if worker_input.command else 'None'}\n\n")
            log.write("Instructions:\n")
            if handoff_path is not None:
                log.write(f"1. Open the Codex-ready handoff at {handoff_path}.\n")
                log.write("2. Paste the handoff into a human-launched Codex or IDE agent.\n")
                log.write("3. Wait for the worker to write result.md, questions.jsonl, or worker_failed.json.\n")
                log.write("4. Run Dev-Flow verification separately after result.md appears.\n\n")
            else:
                log.write(f"1. Please navigate to the workspace directory: {worker_input.workspace_path.resolve()}\n")
                log.write("2. Apply the necessary changes manually in the workspace.\n")
                log.write(f"3. Document your changes by editing .devflow/tasks/{worker_input.task_id}/result.md.\n")
                log.write("4. Once you have completed the changes, run task verification to test them, e.g.:\n")
                log.write(f"   devflow task verify {worker_input.task_id} -- <verification command>\n\n")
            log.write("Awaiting human manual execution...\n")
            log.flush()

        latest = latest_visible_log_line(worker_input.log_file)

        if sys.stdin.isatty() and not getattr(sys.stdin, "_mocked", False):
            print(f"\n[Manual Worker] Handoff generated for task '{worker_input.task_id}'.")
            print(f"Workspace path: {worker_input.workspace_path.resolve()}")
            if handoff_path is not None:
                print(f"Handoff path: {handoff_path}")

        from devflow.control_room.persistence import timestamp

        event = {
            "timestamp": timestamp(),
            "event": "manual_packet_generated",
            "status": "awaiting_human",
            "summary": "Manual instructions generated. Awaiting human workspace changes.",
        }
        try:
            with worker_input.context_file.open("a", encoding="utf-8") as f:
                f.write(json.dumps(event) + "\n")
        except Exception:
            pass

        return WorkerResult(
            status="blocked",
            summary="Manual instructions generated. Awaiting human workspace changes.",
            exit_code=0,
            latest_log_line=latest,
            result_file=worker_input.result_file,
            log_file=worker_input.log_file,
        )


def _build_handoff(worker_input: WorkerInput, agent_id: str) -> str:
    from devflow.control_room.agent_registry import load_agent_registry
    from devflow.control_room.task_packet import build_agent_packet

    agent = load_agent_registry(worker_input.repo_root).require_agent(agent_id)
    packet = build_agent_packet(worker_input.task_id, agent, root=worker_input.repo_root)
    instructions = packet.manual_instructions or ""
    task_root = worker_input.result_file.parent
    rel_task_root = relative_path(worker_input.repo_root, task_root)
    rel_workspace = relative_path(worker_input.repo_root, worker_input.workspace_path)
    return (
        f"# Manual Codex Worker Handoff\n\n"
        f"{instructions}\n\n"
        f"## Concrete Paths\n\n"
        f"- Task ID: {worker_input.task_id}\n"
        f"- Agent ID: {agent_id}\n"
        f"- Workspace: {rel_workspace}\n"
        f"- Evidence directory: {rel_task_root}\n"
        f"- Packet: {relative_path(worker_input.repo_root, task_root / 'packet.json')}\n"
        f"- Complete result: {relative_path(worker_input.repo_root, task_root / 'result.md')}\n"
        f"- Blocked questions: {relative_path(worker_input.repo_root, task_root / 'questions.jsonl')}\n"
        f"- Failure evidence: {relative_path(worker_input.repo_root, task_root / 'worker_failed.json')}\n\n"
        f"## Result.md Contract\n\n"
        f"Write this file only when the work is complete:\n\n"
        f"```markdown\n"
        f"# Result\n\n"
        f"status: complete\n"
        f"summary: <one sentence>\n"
        f"changed_files:\n"
        f"- <workspace-relative path>\n"
        f"verification_suggestion: <command for Dev-Flow to run later>\n"
        f"```\n\n"
        f"## Questions.jsonl Contract\n\n"
        f"Append one JSON object per blocking question:\n\n"
        f"```json\n"
        f'{{"type":"blocked_question","task_id":"{worker_input.task_id}","agent_id":"{agent_id}",'
        f'"question":"<question>","blocking_reason":"<reason>","required_decision":"<decision needed>"}}\n'
        f"```\n\n"
        f"## Worker_failed.json Contract\n\n"
        f"Write this file only when the worker cannot continue:\n\n"
        f"```json\n"
        f'{{"status":"worker_failed","task_id":"{worker_input.task_id}","agent_id":"{agent_id}",'
        f'"summary":"<what failed>","error_type":"<category>","evidence":["<fact>"],'
        f'"next_safe_action":"<single next action>"}}\n'
        f"```\n"
    )


def read_manual_agent_evidence(root: Path, task_id: str, agent_id: str) -> ManualAgentEvidence:
    agent_dir = root / ".devflow" / "tasks" / task_id / "agents" / agent_id
    handoff_path = agent_dir / "handoff.md"
    failed_path = agent_dir / "worker_failed.json"
    questions_path = agent_dir / "questions.jsonl"
    result_path = agent_dir / "result.md"

    failure = _read_failure(failed_path, task_id, agent_id)
    if failure is not None:
        return ManualAgentEvidence(
            state="failed",
            failure_path=relative_path(root, failed_path),
            summary=failure.get("summary"),
            failure=failure.get("summary"),
        )

    question = _read_latest_question(questions_path, task_id, agent_id)
    if question is not None:
        return ManualAgentEvidence(
            state="blocked",
            question_path=relative_path(root, questions_path),
            question=question.get("question"),
            summary=question.get("blocking_reason"),
        )

    result = _read_result(result_path)
    if result is not None:
        return ManualAgentEvidence(
            state="result_present",
            handoff_path=relative_path(root, handoff_path) if handoff_path.exists() else None,
            result_path=relative_path(root, result_path),
            summary=result.get("summary"),
        )

    return ManualAgentEvidence(
        state="awaiting_human",
        handoff_path=relative_path(root, handoff_path) if handoff_path.exists() else None,
    )


def _read_failure(path: Path, task_id: str, agent_id: str) -> dict[str, str] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"summary": "worker_failed.json is not valid JSON"}
    if not isinstance(payload, dict):
        return {"summary": "worker_failed.json must be a JSON object"}
    if payload.get("status") != "worker_failed":
        return {"summary": "worker_failed.json status must be worker_failed"}
    if payload.get("task_id") != task_id or payload.get("agent_id") != agent_id:
        return {"summary": "worker_failed.json task_id or agent_id does not match"}
    summary = payload.get("summary")
    return {"summary": summary if isinstance(summary, str) and summary.strip() else "Worker failed without a summary"}


def _read_latest_question(path: Path, task_id: str, agent_id: str) -> dict[str, str] | None:
    if not path.exists():
        return None
    latest: dict[str, str] | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if (
            isinstance(payload, dict)
            and payload.get("type") == "blocked_question"
            and payload.get("task_id") == task_id
            and payload.get("agent_id") == agent_id
            and isinstance(payload.get("question"), str)
        ):
            latest = {
                "question": payload["question"],
                "blocking_reason": str(payload.get("blocking_reason", "")),
            }
    return latest


def _read_result(path: Path) -> dict[str, str] | None:
    if not path.exists():
        return None
    summary = None
    has_complete_status = False
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped == "status: complete":
            has_complete_status = True
        elif stripped.startswith("summary:"):
            summary = stripped.split(":", 1)[1].strip()
    if not has_complete_status:
        return None
    return {"summary": summary or "Manual worker reported completion."}
