"""Builder-Judge Loop engine.

Implements the quality-control loop pattern:
  1. Human writes the definition of done (the bar)
  2. Builder model creates a draft
  3. Judge model (separate, adversarial) grades 0-100 and lists issues
  4. Builder revises based on judge feedback
  5. Loop until score >= threshold or max rounds
  6. Every round saved as evidence; escalate to human only for important decisions

This is distinct from the goal-autopilot loop in ``loop_engine.py`` which
orchestrates task lifecycle (create → worker → verify → promote).
The builder-judge loop is a content-quality loop: write → grade → fix → repeat.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from devflow.control_room.agent_registry import (
    AgentDefinition,
    ProviderDefinition,
    is_hermes_subscription_agent,
    is_remote_advisory_agent,
    load_agent_registry,
    load_provider_registry,
)
from devflow.control_room.brainstorm import (
    _chat_completion_for_profile,
    _extract_content_for_profile,
    _is_ollama_provider,
    _normalize_raw_response,
)
from devflow.control_room.env_loader import resolve_api_key
from devflow.control_room.openrouter_agent import _redact
from devflow.control_room.paths import devflow_dir, relative_path
from devflow.control_room.persistence import atomic_write_text
from devflow.control_room.stage_artifact import write_stage_artifact as _save_stage_artifact

# Quality gate stages map to builder-judge loop IDs
_QUALITY_GATE_STAGE_PREFIX = "qg-"


BUILDER_JUDGE_SCHEMA_VERSION = 1
DEFAULT_PASS_THRESHOLD = 85
DEFAULT_MAX_ROUNDS = 5
MIN_PASS_THRESHOLD = 50
MAX_PASS_THRESHOLD = 100
MIN_MAX_ROUNDS = 1
MAX_MAX_ROUNDS = 20
MAX_DOD_LENGTH = 10_000
MAX_STARTING_POINT_LENGTH = 20_000
MAX_DRAFT_LENGTH = 50_000

DEFAULT_BUILDER_PROFILE = "deepseek-v4-flash-free-brainstormer"
DEFAULT_JUDGE_PROFILE = "glm-5-2-brainstormer"

LoopStatus = Literal[
    "running",
    "passed",
    "max_rounds",
    "failed",
    "escalated",
]


class BuilderJudgeConfigError(ValueError):
    pass


class BuilderJudgeRunError(ValueError):
    pass


class BuilderJudgeConfig(BaseModel):
    """Configuration for a single builder-judge loop run."""

    definition_of_done: str
    starting_point: str | None = None
    builder_profile_id: str = DEFAULT_BUILDER_PROFILE
    judge_profile_id: str = DEFAULT_JUDGE_PROFILE
    pass_threshold: int = DEFAULT_PASS_THRESHOLD
    max_rounds: int = DEFAULT_MAX_ROUNDS
    escalate_on_max_rounds: bool = True


class BuilderJudgeRound(BaseModel):
    """One round of builder-judge interaction."""

    round_number: int
    draft: str
    score: int | None = None
    judge_feedback: str = ""
    issues: list[str] = Field(default_factory=list)
    passed: bool = False
    builder_profile_id: str
    judge_profile_id: str
    builder_model: str = ""
    judge_model: str = ""
    started_at: str
    finished_at: str
    error: str | None = None


class BuilderJudgeRun(BaseModel):
    """Full run record for a builder-judge loop."""

    schema_version: int = BUILDER_JUDGE_SCHEMA_VERSION
    loop_id: str
    run_id: str
    status: LoopStatus
    config: BuilderJudgeConfig
    rounds: list[BuilderJudgeRound] = Field(default_factory=list)
    final_draft: str | None = None
    final_score: int | None = None
    started_at: str
    finished_at: str | None = None
    evidence_path: str | None = None
    stop_reason: str = ""
    next_safe_action: str = ""


# ── Path helpers ──────────────────────────────────────────────────────────

def builder_judge_dir(root: Path) -> Path:
    return devflow_dir(root) / "builder-judge-loops"


def builder_judge_loop_dir(root: Path, loop_id: str) -> Path:
    return builder_judge_dir(root) / loop_id


def builder_judge_run_path(root: Path, loop_id: str) -> Path:
    return builder_judge_loop_dir(root, loop_id) / "run.json"


def builder_judge_rounds_dir(root: Path, loop_id: str) -> Path:
    return builder_judge_loop_dir(root, loop_id) / "rounds"


# ── Public API ────────────────────────────────────────────────────────────

def run_builder_judge_loop(
    root: Path,
    config: BuilderJudgeConfig,
    *,
    loop_id: str | None = None,
    write_evidence: bool = True,
) -> BuilderJudgeRun:
    """Run the builder-judge loop to completion.

    Each round:
      1. Builder generates (round 1) or revises (round > 1) a draft
      2. Judge grades the draft against the definition of done
      3. If score >= threshold → status ``passed``, stop
      4. If max rounds reached without passing → status ``max_rounds``
         (or ``escalated`` if ``escalate_on_max_rounds`` is True)

    All rounds are persisted as evidence.
    """
    root = root.resolve()
    _validate_config(config)

    loop_id = loop_id or _generate_loop_id()
    run_id = _generate_run_id(loop_id)
    started_at = _now()

    run = BuilderJudgeRun(
        loop_id=loop_id,
        run_id=run_id,
        status="running",
        config=config,
        started_at=started_at,
        finished_at=started_at,
        stop_reason="",
        next_safe_action="",
    )

    builder_profile, builder_provider = _load_profile(root, config.builder_profile_id)
    judge_profile, judge_provider = _load_profile(root, config.judge_profile_id)

    if config.builder_profile_id == config.judge_profile_id:
        raise BuilderJudgeConfigError(
            "Builder and judge must be different models. "
            f"Both were set to '{config.builder_profile_id}'. "
            "The adversarial gap between builder and judge is the whole point."
        )

    builder_api_key = _resolve_api_key(builder_provider)
    judge_api_key = _resolve_api_key(judge_provider)

    current_draft = config.starting_point or ""

    for round_number in range(1, config.max_rounds + 1):
        round_started = _now()

        # ── 1. Builder writes / revises ───────────────────────────────
        try:
            if round_number == 1 and current_draft:
                builder_prompt = _builder_revise_prompt(
                    config.definition_of_done,
                    current_draft,
                    None,
                )
            elif round_number == 1:
                builder_prompt = _builder_initial_prompt(config.definition_of_done)
            else:
                prev_round = run.rounds[-1]
                builder_prompt = _builder_revise_prompt(
                    config.definition_of_done,
                    current_draft,
                    prev_round,
                )

            builder_response = _chat_completion_for_profile(
                profile=builder_profile,
                provider=builder_provider,
                system_prompt=_builder_system_prompt(builder_profile),
                user_prompt=builder_prompt,
                api_key=builder_api_key,
            )
            raw_builder = _normalize_raw_response(builder_response, api_key=builder_api_key)
            draft = _extract_content_for_profile(provider=builder_provider, response_body=builder_response)
            draft = _clean_draft(draft)
        except Exception as exc:
            error = _redact(str(exc), api_key=builder_api_key or "") if builder_api_key else str(exc)
            round_record = BuilderJudgeRound(
                round_number=round_number,
                draft=current_draft,
                builder_profile_id=builder_profile.id,
                judge_profile_id=judge_profile.id,
                builder_model=builder_profile.model,
                judge_model=judge_profile.model,
                started_at=round_started,
                finished_at=_now(),
                error=f"Builder failed: {error}",
            )
            run.rounds.append(round_record)
            run.status = "failed"
            run.stop_reason = f"builder_error_round_{round_number}"
            run.next_safe_action = "Check builder model availability and API key, then rerun."
            return _finish(root, run, write_evidence=write_evidence)

        current_draft = draft

        # ── 2. Judge grades ───────────────────────────────────────────
        try:
            judge_response = _chat_completion_for_profile(
                profile=judge_profile,
                provider=judge_provider,
                system_prompt=_judge_system_prompt(judge_profile),
                user_prompt=_judge_user_prompt(config.definition_of_done, draft),
                api_key=judge_api_key,
            )
            raw_judge = _normalize_raw_response(judge_response, api_key=judge_api_key)
            judge_content = _extract_content_for_profile(provider=judge_provider, response_body=judge_response)
            score, issues, feedback = _parse_judge_response(judge_content)
        except Exception as exc:
            error = _redact(str(exc), api_key=judge_api_key or "") if judge_api_key else str(exc)
            round_record = BuilderJudgeRound(
                round_number=round_number,
                draft=draft,
                builder_profile_id=builder_profile.id,
                judge_profile_id=judge_profile.id,
                builder_model=builder_profile.model,
                judge_model=judge_profile.model,
                started_at=round_started,
                finished_at=_now(),
                error=f"Judge failed: {error}",
            )
            run.rounds.append(round_record)
            run.status = "failed"
            run.stop_reason = f"judge_error_round_{round_number}"
            run.next_safe_action = "Check judge model availability and API key, then rerun."
            return _finish(root, run, write_evidence=write_evidence)

        passed = score is not None and score >= config.pass_threshold

        round_record = BuilderJudgeRound(
            round_number=round_number,
            draft=draft,
            score=score,
            judge_feedback=feedback,
            issues=issues,
            passed=passed,
            builder_profile_id=builder_profile.id,
            judge_profile_id=judge_profile.id,
            builder_model=builder_profile.model,
            judge_model=judge_profile.model,
            started_at=round_started,
            finished_at=_now(),
        )
        run.rounds.append(round_record)

        # Save per-round evidence
        if write_evidence:
            _write_round_evidence(root, loop_id, round_record, raw_builder, raw_judge)
            _write_run_evidence(root, run)  # incremental state for polling

        if passed:
            run.status = "passed"
            run.final_draft = draft
            run.final_score = score
            run.stop_reason = f"passed_round_{round_number}"
            run.next_safe_action = "Loop passed. Review the final draft."
            return _finish(root, run, write_evidence=write_evidence)

    # Max rounds reached
    run.final_draft = current_draft
    run.final_score = run.rounds[-1].score if run.rounds else None

    if config.escalate_on_max_rounds:
        run.status = "escalated"
        run.stop_reason = (
            f"max_rounds_{config.max_rounds}_reached_without_passing_"
            f"last_score_{run.final_score}"
        )
        run.next_safe_action = (
            "Loop reached max rounds without passing. "
            "Review the best draft and judge feedback, then decide: "
            "rerun with higher max_rounds, adjust the definition of done, "
            "or accept the current draft."
        )
        # Create a Dev-Flow question so this surfaces in the operator's queue
        _create_escalation_question(root, run)
    else:
        run.status = "max_rounds"
        run.stop_reason = f"max_rounds_{config.max_rounds}_reached"
        run.next_safe_action = "Rerun with higher max_rounds or adjust the definition of done."

    return _finish(root, run, write_evidence=write_evidence)


def list_builder_judge_loops(root: Path) -> list[dict[str, Any]]:
    """List all builder-judge loop runs, newest first."""
    directory = builder_judge_dir(root)
    if not directory.exists():
        return []
    results: list[dict[str, Any]] = []
    for entry in sorted(directory.iterdir()):
        run_file = entry / "run.json"
        if not run_file.exists():
            continue
        try:
            data = json.loads(run_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        results.append({
            "loop_id": data.get("loop_id", entry.name),
            "run_id": data.get("run_id", ""),
            "status": data.get("status", "unknown"),
            "started_at": data.get("started_at", ""),
            "finished_at": data.get("finished_at", ""),
            "final_score": data.get("final_score"),
            "rounds_completed": len(data.get("rounds", [])),
            "definition_of_done": (data.get("config", {}).get("definition_of_done", ""))[:200],
            "builder_profile_id": data.get("config", {}).get("builder_profile_id", ""),
            "judge_profile_id": data.get("config", {}).get("judge_profile_id", ""),
        })
    results.sort(key=lambda r: r.get("started_at", ""), reverse=True)
    return results


def get_builder_judge_run(root: Path, loop_id: str) -> dict[str, Any] | None:
    """Get the full run record for a builder-judge loop."""
    path = builder_judge_run_path(root, loop_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


# ── Validation ────────────────────────────────────────────────────────────

def _validate_config(config: BuilderJudgeConfig) -> None:
    dod = config.definition_of_done.strip()
    if not dod:
        raise BuilderJudgeConfigError("definition_of_done must not be empty — this is the bar.")
    if len(dod) > MAX_DOD_LENGTH:
        raise BuilderJudgeConfigError(
            f"definition_of_done exceeds {MAX_DOD_LENGTH} characters."
        )
    if config.starting_point and len(config.starting_point) > MAX_STARTING_POINT_LENGTH:
        raise BuilderJudgeConfigError(
            f"starting_point exceeds {MAX_STARTING_POINT_LENGTH} characters."
        )
    if not (MIN_PASS_THRESHOLD <= config.pass_threshold <= MAX_PASS_THRESHOLD):
        raise BuilderJudgeConfigError(
            f"pass_threshold must be between {MIN_PASS_THRESHOLD} and {MAX_PASS_THRESHOLD}."
        )
    if not (MIN_MAX_ROUNDS <= config.max_rounds <= MAX_MAX_ROUNDS):
        raise BuilderJudgeConfigError(
            f"max_rounds must be between {MIN_MAX_ROUNDS} and {MAX_MAX_ROUNDS}."
        )


# ── Model loading ─────────────────────────────────────────────────────────

def _load_profile(root: Path, profile_id: str) -> tuple[AgentDefinition, ProviderDefinition]:
    agent = load_agent_registry(root).require_agent(profile_id)
    provider = load_provider_registry(root).require_provider(agent.provider)
    is_ollama = _is_ollama_provider(provider)
    is_hermes_profile = is_hermes_subscription_agent(agent, provider=provider)
    if not is_ollama and not is_hermes_profile and not is_remote_advisory_agent(agent, provider=provider):
        raise BuilderJudgeConfigError(
            f"Profile '{profile_id}' is not an advisory or Ollama profile "
            f"and cannot be used for builder-judge loops."
        )
    return agent, provider


def _resolve_api_key(provider: ProviderDefinition) -> str | None:
    if _is_ollama_provider(provider) or provider.adapter == "hermes_profile":
        return None
    api_key_env = provider.api_key_env or "OPENROUTER_API_KEY"
    return resolve_api_key(api_key_env)


# ── Prompts ───────────────────────────────────────────────────────────────

def _builder_system_prompt(profile: AgentDefinition) -> str:
    return (
        f"You are {profile.model}, the Builder in a Dev-Flow Builder-Judge Loop. "
        f"Your job is to produce content that meets a specific Definition of Done. "
        f"You will receive the bar, your previous draft (if any), and the Judge's "
        f"specific feedback and issues. Your task: produce the best possible revision. "
        f"Address every issue the Judge raised. Do not explain yourself — just output "
        f"the content. Return ONLY the content, no meta-commentary, no JSON."
    )


def _builder_initial_prompt(definition_of_done: str) -> str:
    return (
        f"## Definition of Done\n\n{definition_of_done}\n\n"
        f"## Task\n\nProduce the content that meets the above bar. "
        f"Output only the content."
    )


def _builder_revise_prompt(
    definition_of_done: str,
    current_draft: str,
    prev_round: BuilderJudgeRound | None,
) -> str:
    parts = [f"## Definition of Done\n\n{definition_of_done}\n"]
    parts.append(f"## Current Draft\n\n{current_draft}\n")
    if prev_round and prev_round.issues:
        parts.append("## Judge Feedback (Round %d, Score: %s)\n" % (
            prev_round.round_number,
            prev_round.score if prev_round.score is not None else "N/A",
        ))
        parts.append(prev_round.judge_feedback + "\n")
        parts.append("## Specific Issues to Fix\n")
        for issue in prev_round.issues:
            parts.append(f"- {issue}")
        parts.append("")
    parts.append(
        "## Task\n\nRevise the draft to address every issue above and meet the "
        "Definition of Done. Output only the revised content."
    )
    return "\n".join(parts)


def _judge_system_prompt(profile: AgentDefinition) -> str:
    return (
        f"You are {profile.model}, the Judge in a Dev-Flow Builder-Judge Loop. "
        f"You are adversarial. Your job is to grade the Builder's draft against "
        f"a specific Definition of Done. Score 0-100. Be harsh — find the holes, "
        f"the gaps, the missing pieces. List every specific issue. "
        f"Return JSON with keys: score (integer 0-100), issues (array of strings), "
        f"feedback (string summary). Do not rubber-stamp. If the draft is perfect, "
        f"score 100. If it misses the bar entirely, score below 50."
    )


def _judge_user_prompt(definition_of_done: str, draft: str) -> str:
    return (
        f"## Definition of Done\n\n{definition_of_done}\n\n"
        f"## Draft to Grade\n\n{draft}\n\n"
        f"## Task\n\nGrade this draft against the Definition of Done. "
        f"Return JSON: {{\"score\": <0-100>, \"issues\": [\"...\"], "
        f"\"feedback\": \"...\"}}"
    )


# ── Judge response parsing ────────────────────────────────────────────────

def _parse_judge_response(content: str) -> tuple[int | None, list[str], str]:
    """Parse the judge's JSON response into (score, issues, feedback)."""
    stripped = content.strip()

    # Try to extract JSON from the response
    json_payload = _extract_json(stripped)
    if json_payload is not None:
        score = _safe_int(json_payload.get("score"))
        issues_raw = json_payload.get("issues", [])
        issues = _normalize_issues(issues_raw)
        feedback = str(json_payload.get("feedback", "")).strip()
        return score, issues, feedback

    # Fallback: try to find a score with regex
    score_match = re.search(r'\b(?:score|grade)\s*[:=]\s*(\d{1,3})\b', stripped, re.IGNORECASE)
    score = int(score_match.group(1)) if score_match else None
    if score is not None and score > 100:
        score = None
    return score, [], stripped


def _extract_json(text: str) -> dict[str, Any] | None:
    """Try to extract a JSON object from the text."""
    # Try direct parse
    try:
        payload = json.loads(text)
        if isinstance(payload, dict):
            return payload
    except json.JSONDecodeError:
        pass

    # Try to find JSON between { and }
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    payload = json.loads(text[start : i + 1])
                    if isinstance(payload, dict):
                        return payload
                except json.JSONDecodeError:
                    pass
    return None


def _safe_int(value: Any) -> int | None:
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return None
    return None


def _normalize_issues(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _clean_draft(text: str) -> str:
    """Clean up the builder's output — strip whitespace, cap length."""
    cleaned = text.strip()
    if len(cleaned) > MAX_DRAFT_LENGTH:
        cleaned = cleaned[:MAX_DRAFT_LENGTH] + "\n\n[... truncated at {} chars]".format(MAX_DRAFT_LENGTH)
    return cleaned


# ── Evidence persistence ──────────────────────────────────────────────────

def _finish(root: Path, run: BuilderJudgeRun, *, write_evidence: bool) -> BuilderJudgeRun:
    run.finished_at = _now()
    if write_evidence:
        _write_run_evidence(root, run)
    return run


def _write_run_evidence(root: Path, run: BuilderJudgeRun) -> None:
    loop_dir = builder_judge_loop_dir(root, run.loop_id)
    loop_dir.mkdir(parents=True, exist_ok=True)
    run_path = builder_judge_run_path(root, run.loop_id)
    run.evidence_path = relative_path(root, run_path)
    atomic_write_text(run_path, json.dumps(run.model_dump(mode="json"), indent=2, sort_keys=False) + "\n")


def _write_round_evidence(
    root: Path,
    loop_id: str,
    round_record: BuilderJudgeRound,
    raw_builder: str,
    raw_judge: str,
) -> None:
    rounds_dir = builder_judge_rounds_dir(root, loop_id)
    rounds_dir.mkdir(parents=True, exist_ok=True)
    round_num = round_record.round_number

    round_path = rounds_dir / f"round-{round_num:02d}.json"
    atomic_write_text(round_path, json.dumps(round_record.model_dump(mode="json"), indent=2) + "\n")

    builder_raw_path = rounds_dir / f"round-{round_num:02d}-builder.raw.json"
    atomic_write_text(builder_raw_path, raw_builder + "\n")

    judge_raw_path = rounds_dir / f"round-{round_num:02d}-judge.raw.json"
    atomic_write_text(judge_raw_path, raw_judge + "\n")


# ── Utilities ─────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _generate_loop_id() -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"bj-{ts}"


def _generate_run_id(loop_id: str) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"{loop_id}-run-{ts}"


# ── Pipeline quality gate ─────────────────────────────────────────────────


def _create_escalation_question(root: Path, run: BuilderJudgeRun) -> None:
    """Create a Dev-Flow question record for an escalated builder-judge loop.

    This surfaces the escalation in the operator's question queue so it can be
    resolved through the normal review flow.
    """
    import hashlib

    question_dir = root / ".devflow" / "questions"
    question_dir.mkdir(parents=True, exist_ok=True)

    raw_id = f"builder-judge|{run.loop_id}|escalated"
    digest = hashlib.sha256(raw_id.encode("utf-8")).hexdigest()[:12]
    question_id = f"Q-bj-{digest}"

    question_record = {
        "schema_version": 1,
        "question_id": question_id,
        "status": "open",
        "task_id": run.loop_id,
        "agent_id": run.config.judge_profile_id,
        "source_path": run.evidence_path or "",
        "source_line": None,
        "question": (
            f"Builder-Judge loop '{run.loop_id}' reached max rounds ({run.config.max_rounds}) "
            f"without passing. Last score: {run.final_score}/{run.config.pass_threshold}. "
            f"Review the draft and decide: rerun, adjust the definition of done, or accept."
        ),
        "blocking_reason": "builder-judge loop did not meet the pass threshold",
        "required_decision": (
            "Accept the current draft, rerun with adjusted parameters, "
            "or revise the definition of done."
        ),
        "answer": None,
        "answered_at": None,
        "resolved_at": None,
        "resolved_reason": None,
        "recommended_resume_command": f"devflow builder-judge show {run.loop_id}",
        "answer_path": None,
        "evidence_paths": [run.evidence_path] if run.evidence_path else [],
        "warnings": [],
    }

    question_path = question_dir / f"{question_id}.json"
    atomic_write_text(question_path, json.dumps(question_record, indent=2) + "\n")


SPEC_QUALITY_DOD = (
    "A complete specification document that: "
    "(1) captures every decision made in the brainstorm transcript, "
    "(2) lists clear functional requirements as bullet points, "
    "(3) identifies scope boundaries — what is explicitly out of scope, "
    "(4) notes any open questions or risks, "
    "(5) is written in clear markdown with a title and sections, "
    "(6) does not invent features that were not discussed."
)

PLAN_QUALITY_DOD = (
    "A complete implementation plan that: "
    "(1) breaks down the work into concrete, ordered steps, "
    "(2) each step has a clear deliverable and verification method, "
    "(3) identifies which files or components will be touched, "
    "(4) notes dependencies between steps, "
    "(5) includes a testing/verification strategy, "
    "(6) is written in clear markdown with a title and sections, "
    "(7) does not include steps for features not in the spec."
)

QUALITY_GATE_DODS = {
    "spec": SPEC_QUALITY_DOD,
    "plan": PLAN_QUALITY_DOD,
}


def run_quality_gate(
    root: Path,
    *,
    stage: str,
    session_id: str | None = None,
    transcript_text: str = "",
    builder_profile_id: str = DEFAULT_BUILDER_PROFILE,
    judge_profile_id: str = DEFAULT_JUDGE_PROFILE,
    pass_threshold: int = DEFAULT_PASS_THRESHOLD,
    max_rounds: int = 3,
    starting_point: str | None = None,
    write_evidence: bool = True,
) -> BuilderJudgeRun:
    """Run a builder-judge loop as a quality gate for spec or plan generation.

    The builder generates a spec/plan from the brainstorm transcript, and the
    judge grades it against a stage-specific definition of done. The loop
    iterates until the output passes or max rounds is reached.

    Also writes StageArtifact to record gate status in the pipeline.
    """
    if stage not in QUALITY_GATE_DODS:
        raise BuilderJudgeConfigError(
            f"Unknown quality-gate stage: {stage}. Must be 'spec' or 'plan'.",
        )

    dod = QUALITY_GATE_DODS[stage]
    # Prepend the transcript to the definition of done as context
    full_dod = (
        f"{dod}\n\n"
        f"## Brainstorm Transcript (source material)\n\n{transcript_text}"
    )

    config = BuilderJudgeConfig(
        definition_of_done=full_dod,
        starting_point=starting_point,
        builder_profile_id=builder_profile_id,
        judge_profile_id=judge_profile_id,
        pass_threshold=pass_threshold,
        max_rounds=max_rounds,
        escalate_on_max_rounds=True,
    )
    run = run_builder_judge_loop(
        root,
        config,
        loop_id=f"qg-{stage}-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}",
        write_evidence=write_evidence,
    )

    # Persist StageArtifact from quality-gate result.
    if session_id and write_evidence:
        root = root.resolve()
        loop_dir = builder_judge_loop_dir(root, run.loop_id)
        final_draft_path = loop_dir / "final_draft.md"
        if run.final_draft:
            atomic_write_text(final_draft_path, run.final_draft.rstrip() + "\n")
        quality_gate_path = root / run.evidence_path if run.evidence_path else None
        stage_status = "passed" if run.status == "passed" else "escalated" if run.status == "escalated" else "draft"
        _save_stage_artifact(
            root=root,
            session_id=session_id,
            stage=stage,  # type: ignore[arg-type]
            source="builder_judge",
            status=stage_status,
            artifact_path=final_draft_path if run.final_draft else quality_gate_path or loop_dir,
            quality_gate_path=quality_gate_path,
            score=run.final_score,
            next_action=f"Quality gate {run.status}. Review draft and decide: accept, rerun, or escalate.",
        )

    return run
