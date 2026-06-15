from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from devflow.control_room.paths import relative_path, task_dir
from devflow.control_room.persistence import atomic_write_text, list_tasks
from devflow.control_room.task_lifecycle import append_task_event


QuestionStatus = Literal["open", "answered", "resolved"]


class QuestionRecord(BaseModel):
    schema_version: int = 1
    question_id: str
    status: QuestionStatus
    task_id: str
    agent_id: str | None = None
    source_path: str
    source_line: int | None = None
    question: str
    blocking_reason: str | None = None
    required_decision: str | None = None
    answer: str | None = None
    answered_at: str | None = None
    resolved_at: str | None = None
    resolved_reason: str | None = None
    recommended_resume_command: str
    answer_path: str | None = None
    evidence_paths: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class QuestionSnapshot(BaseModel):
    schema_version: int = 1
    generated_at: str
    counts: dict[str, int]
    questions: list[QuestionRecord] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    evidence_paths: list[str] = Field(default_factory=list)
    next_safe_action: str


def question_id_for_source(
    *,
    task_id: str,
    agent_id: str | None,
    source_path: str,
    source_line: int | None,
    question: str,
) -> str:
    raw = f"{task_id}|{agent_id or ''}|{source_path}|{source_line or 0}|{question}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]
    return f"Q-{task_id}-{digest}"


def build_question_snapshot(root: Path) -> QuestionSnapshot:
    root = root.resolve()
    source_questions, warnings, evidence_paths = _scan_source_questions(root)
    persisted = _read_persisted_questions(root)
    by_id = {question.question_id: question for question in source_questions}

    for question in persisted:
        existing = by_id.get(question.question_id)
        if existing is None:
            question.warnings.append("source question evidence is missing")
            by_id[question.question_id] = question
            continue
        merged = existing.model_copy(update=question.model_dump(exclude={"evidence_paths", "warnings"}))
        merged.evidence_paths = _dedupe([*existing.evidence_paths, *question.evidence_paths])
        merged.warnings = _dedupe([*existing.warnings, *question.warnings])
        by_id[question.question_id] = merged

    questions = sorted(by_id.values(), key=lambda item: (item.status != "open", item.task_id, item.question_id))
    counts = {"open": 0, "answered": 0, "resolved": 0}
    for question in questions:
        counts[question.status] = counts.get(question.status, 0) + 1

    next_action = "devflow task list"
    first_open = next((question for question in questions if question.status == "open"), None)
    if first_open is not None:
        next_action = f'devflow question answer {first_open.question_id} --answer "<answer>"'

    return QuestionSnapshot(
        generated_at=datetime.now(timezone.utc).isoformat(),
        counts=counts,
        questions=questions,
        warnings=warnings,
        evidence_paths=_dedupe(evidence_paths + [path for q in questions for path in q.evidence_paths]),
        next_safe_action=next_action,
    )


def answer_question(root: Path, question_id: str, *, answer: str, resume_command: str | None = None) -> QuestionRecord:
    clean_answer = answer.strip()
    if not clean_answer:
        raise ValueError("Answer is required.")
    question = _find_question(root, question_id)
    command = (resume_command or question.recommended_resume_command).strip()
    if not command.startswith("devflow "):
        raise ValueError("Resume command must be a devflow command.")
    now = datetime.now(timezone.utc).isoformat()
    updated = question.model_copy(
        update={
            "status": "answered",
            "answer": clean_answer,
            "answered_at": now,
            "recommended_resume_command": command,
        }
    )
    return _write_question_record(root, updated, "question_answered", {"answer_path": _record_relpath(question_id)})


def resolve_question(root: Path, question_id: str, *, reason: str) -> QuestionRecord:
    clean_reason = reason.strip()
    if not clean_reason:
        raise ValueError("Resolve reason is required.")
    question = _find_question(root, question_id)
    now = datetime.now(timezone.utc).isoformat()
    updated = question.model_copy(
        update={
            "status": "resolved",
            "resolved_at": now,
            "resolved_reason": clean_reason,
        }
    )
    return _write_question_record(root, updated, "question_resolved", {"reason": clean_reason})


def render_question_snapshot(snapshot: QuestionSnapshot) -> str:
    lines = [
        f"open_questions: {snapshot.counts.get('open', 0)}",
        f"answered_questions: {snapshot.counts.get('answered', 0)}",
        f"resolved_questions: {snapshot.counts.get('resolved', 0)}",
        f"next_safe_action: {snapshot.next_safe_action}",
    ]
    open_questions = [question for question in snapshot.questions if question.status == "open"]
    if open_questions:
        lines.append("questions:")
        for question in open_questions:
            lines.append(f"  - {question.question_id}: {question.question}")
            lines.append(f"    task: {question.task_id}")
            lines.append(f'    answer: devflow question answer {question.question_id} --answer "<answer>"')
    if snapshot.warnings:
        lines.append("warnings:")
        for warning in snapshot.warnings:
            lines.append(f"  - {warning}")
    return "\n".join(lines) + "\n"


def _scan_source_questions(root: Path) -> tuple[list[QuestionRecord], list[str], list[str]]:
    questions: list[QuestionRecord] = []
    warnings: list[str] = []
    evidence_paths: list[str] = []
    for task in list_tasks(root):
        current_task_dir = task_dir(root, task.id)
        candidates = [current_task_dir / "questions.jsonl"]
        agents_dir = current_task_dir / "agents"
        if agents_dir.exists():
            candidates.extend(sorted(agents_dir.glob("*/questions.jsonl")))
        for path in candidates:
            if not path.exists():
                continue
            rel = relative_path(root, path)
            evidence_paths.append(rel)
            for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                if not raw_line.strip():
                    continue
                payload = _parse_question_line(raw_line, rel, line_number, warnings)
                if payload is None:
                    continue
                question_text = str(payload["question"]).strip()
                agent_id = payload.get("agent_id")
                agent_id_text = str(agent_id) if agent_id else None
                question_id = question_id_for_source(
                    task_id=task.id,
                    agent_id=agent_id_text,
                    source_path=rel,
                    source_line=line_number,
                    question=question_text,
                )
                questions.append(
                    QuestionRecord(
                        question_id=question_id,
                        status="open",
                        task_id=task.id,
                        agent_id=agent_id_text,
                        source_path=rel,
                        source_line=line_number,
                        question=question_text,
                        blocking_reason=_optional_text(payload.get("blocking_reason")),
                        required_decision=_optional_text(payload.get("required_decision")),
                        recommended_resume_command=f"devflow task next-action {task.id}",
                        evidence_paths=[rel],
                    )
                )
    return questions, warnings, evidence_paths


def _parse_question_line(
    raw_line: str,
    source_path: str,
    line_number: int,
    warnings: list[str],
) -> dict[str, object] | None:
    try:
        payload = json.loads(raw_line)
    except json.JSONDecodeError as exc:
        warnings.append(f"{source_path}:{line_number}: invalid JSON ({exc.msg})")
        return None
    if not isinstance(payload, dict):
        warnings.append(f"{source_path}:{line_number}: expected JSON object")
        return None
    if payload.get("type") != "blocked_question":
        warnings.append(f"{source_path}:{line_number}: type must be blocked_question")
        return None
    if not isinstance(payload.get("question"), str) or not payload["question"].strip():
        warnings.append(f"{source_path}:{line_number}: question is required")
        return None
    return payload


def _read_persisted_questions(root: Path) -> list[QuestionRecord]:
    question_dir = root / ".devflow" / "questions"
    if not question_dir.exists():
        return []
    records: list[QuestionRecord] = []
    for path in sorted(question_dir.glob("*.json")):
        try:
            records.append(QuestionRecord.model_validate_json(path.read_text(encoding="utf-8")))
        except ValueError:
            continue
    return records


def _find_question(root: Path, question_id: str) -> QuestionRecord:
    for question in build_question_snapshot(root).questions:
        if question.question_id == question_id:
            return question
    raise ValueError(f"Unknown question id: {question_id}")


def _write_question_record(
    root: Path,
    question: QuestionRecord,
    event_name: str,
    details: dict[str, str],
) -> QuestionRecord:
    root = root.resolve()
    project_path = root / _record_relpath(question.question_id)
    mirror_path = task_dir(root, question.task_id) / "question-answers" / f"{question.question_id}.json"
    rel_project = relative_path(root, project_path)
    rel_mirror = relative_path(root, mirror_path)
    updated = question.model_copy(
        update={
            "answer_path": rel_project,
            "evidence_paths": _dedupe([*question.evidence_paths, rel_project, rel_mirror]),
        }
    )
    payload = updated.model_dump_json(indent=2) + "\n"
    atomic_write_text(project_path, payload)
    atomic_write_text(mirror_path, payload)
    append_task_event(root, question.task_id, event_name, {"question_id": question.question_id, **details})
    return updated


def _record_relpath(question_id: str) -> str:
    return f".devflow/questions/{question_id}.json"


def _optional_text(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result
