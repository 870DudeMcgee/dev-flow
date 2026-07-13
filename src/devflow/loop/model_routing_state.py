"""Role-specific model scores, health state, ranking, and concurrency limits."""

from __future__ import annotations

import json
import os
import fcntl
from contextlib import contextmanager
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Mapping, Sequence


MAX_ACTIVE_SUBAGENTS = 8
MAX_ACTIVE_WRITERS = 4
MAX_RESIDENT_LOCAL_TASKS = 3
MIN_ROUTINE_OUTPUT_TPS = 5.0
MIN_SPEED_SAMPLES = 3
OBSERVED_DOMINANCE_SAMPLE_COUNT = 5

ROLE_PROFILE_MAP = {
    "brainstorm": "planning-specification",
    "planner": "planning-specification",
    "planning_judge": "judge-reviewer",
    "builder": "builder",
    "judge": "judge-reviewer",
    "build_judge": "judge-reviewer",
    "verifier": "judge-reviewer",
    "final_judge": "judge-reviewer",
}


def _bounded_score(value: float) -> float:
    return round(max(0.0, min(100.0, float(value))), 2)


@dataclass(frozen=True)
class ModelRoleScore:
    """Evidence accumulated for one model in one worker profile."""

    model_id: str
    profile: str
    prior_score: float
    observed_quality_total: float = 0.0
    sample_count: int = 0
    human_feedback_total: float = 0.0
    human_feedback_count: int = 0
    human_accept_count: int = 0
    human_reject_count: int = 0
    human_correction_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    speed_total: float = 0.0
    speed_sample_count: int = 0
    health: str = "healthy"
    quarantine_reason: str = ""

    @property
    def confidence(self) -> str:
        if self.sample_count == 0:
            return "advertised"
        if self.sample_count < OBSERVED_DOMINANCE_SAMPLE_COUNT:
            return "provisional"
        if self.sample_count < 10:
            return "medium"
        return "high"

    @property
    def quality_score(self) -> float:
        prior = _bounded_score(self.prior_score)
        if self.sample_count:
            observed = self.observed_quality_total / self.sample_count
            if self.sample_count < OBSERVED_DOMINANCE_SAMPLE_COUNT:
                observed_weight = self.sample_count * 0.1
            else:
                observed_weight = min(0.9, 0.7 + ((self.sample_count - 5) * 0.02))
            combined = (prior * (1.0 - observed_weight)) + (observed * observed_weight)
        else:
            combined = prior
        if self.human_feedback_count:
            human = self.human_feedback_total / self.human_feedback_count
            combined = (human * 0.75) + (combined * 0.25)
        return _bounded_score(combined)

    @property
    def reliability_score(self) -> float:
        total = self.success_count + self.failure_count
        if total == 0:
            return 100.0
        return _bounded_score(100.0 * (self.success_count + 4) / (total + 4))

    @property
    def speed_score(self) -> float | None:
        if self.speed_sample_count == 0:
            return None
        return round(self.speed_total / self.speed_sample_count, 2)

    @property
    def routine_eligible(self) -> bool:
        if self.health != "healthy":
            return False
        speed = self.speed_score
        return not (
            self.speed_sample_count >= MIN_SPEED_SAMPLES
            and speed is not None
            and speed < MIN_ROUTINE_OUTPUT_TPS
        )


@dataclass(frozen=True)
class ConcurrencyUsage:
    """Current overlapping worker usage."""

    total: int = 0
    writers: int = 0
    local_heavy: int = 0


def _capabilities(model: Mapping[str, object]) -> Mapping[str, object]:
    value = model.get("capabilities")
    return value if isinstance(value, Mapping) else {}


def seed_role_score(model: Mapping[str, object], profile: str) -> ModelRoleScore:
    """Create a transparent advertised prior for one eligible profile."""

    capabilities = _capabilities(model)
    base = 50.0
    role_weights: dict[str, dict[str, float]] = {
        "builder": {
            "coding": 15,
            "tool_calling": 10,
            "structured_output": 10,
            "reasoning": 5,
            "long_context": 5,
        },
        "code-scout": {
            "coding": 20,
            "tool_calling": 10,
            "long_context": 10,
            "reasoning": 5,
        },
        "judge-reviewer": {
            "reasoning": 20,
            "structured_output": 10,
            "long_context": 10,
            "tool_calling": 5,
        },
        "planning-specification": {
            "reasoning": 15,
            "long_context": 15,
            "structured_output": 10,
            "tool_calling": 5,
        },
        "research-scout": {
            "tool_calling": 15,
            "reasoning": 10,
            "long_context": 10,
            "structured_output": 5,
        },
        "vision-research": {
            "image_input": 25,
            "reasoning": 10,
            "tool_calling": 5,
            "long_context": 5,
        },
        "classifier-safety": {
            "reasoning": 15,
            "structured_output": 15,
            "long_context": 5,
        },
    }
    for capability, weight in role_weights.get(profile, {}).items():
        if capabilities.get(capability) is True:
            base += weight
    return ModelRoleScore(
        model_id=str(model.get("id") or ""),
        profile=profile,
        prior_score=_bounded_score(base),
    )


def record_role_outcome(
    score: ModelRoleScore,
    *,
    quality: float | None = None,
    human_score: float | None = None,
    success: bool | None = None,
    fault_kind: str = "",
    output_tokens_per_second: float | None = None,
) -> ModelRoleScore:
    """Record separated quality, reliability, speed, and human evidence."""

    updates: dict[str, object] = {}
    if quality is not None:
        updates["observed_quality_total"] = score.observed_quality_total + _bounded_score(quality)
        updates["sample_count"] = score.sample_count + 1
    if human_score is not None:
        updates["human_feedback_total"] = score.human_feedback_total + _bounded_score(human_score)
        updates["human_feedback_count"] = score.human_feedback_count + 1
    if success is True:
        updates["success_count"] = score.success_count + 1
    elif success is False:
        updates["failure_count"] = score.failure_count + 1
    if output_tokens_per_second is not None:
        updates["speed_total"] = score.speed_total + max(0.0, float(output_tokens_per_second))
        updates["speed_sample_count"] = score.speed_sample_count + 1
    # fault_kind is intentionally classified by the caller. Infrastructure
    # failures update reliability through success=False but never quality.
    _ = fault_kind
    return replace(score, **updates)


def record_human_role_feedback(
    score: ModelRoleScore,
    *,
    decision: str,
) -> ModelRoleScore:
    """Apply one explicit accept/reject/correction as the strongest signal."""

    normalized = decision.strip().lower()
    score_by_decision = {
        "accept": 100.0,
        "reject": 0.0,
        "correction": 50.0,
    }
    if normalized not in score_by_decision:
        raise ValueError(f"Unknown human feedback decision: {decision}")
    updates = {
        "human_feedback_total": (
            score.human_feedback_total + score_by_decision[normalized]
        ),
        "human_feedback_count": score.human_feedback_count + 1,
    }
    counter = {
        "accept": "human_accept_count",
        "reject": "human_reject_count",
        "correction": "human_correction_count",
    }[normalized]
    updates[counter] = getattr(score, counter) + 1
    return replace(score, **updates)


def quarantine_role(score: ModelRoleScore, *, reason: str) -> ModelRoleScore:
    """Quarantine one eligible model/profile pairing pending human review."""

    return replace(score, health="quarantined", quarantine_reason=reason.strip())


def restore_role(score: ModelRoleScore, *, human_approved: bool) -> ModelRoleScore:
    """Restore a quarantined role only through an explicit human decision."""

    if not human_approved:
        raise ValueError("Model-role restoration requires explicit human approval.")
    return replace(score, health="healthy", quarantine_reason="")


def rank_free_cloud_models(
    models: Sequence[Mapping[str, object]],
    profile: str,
    *,
    scores: Mapping[str, ModelRoleScore] | None = None,
    limit: int = 3,
) -> list[ModelRoleScore]:
    """Rank capable healthy free models for one profile, capped per task."""

    score_map = scores or {}
    ranked: list[ModelRoleScore] = []
    for model in models:
        if model.get("cost_class") != "free_cloud" or model.get("health") == "quarantined":
            continue
        profiles = model.get("eligible_profiles")
        if not isinstance(profiles, list) or profile not in profiles:
            continue
        model_id = str(model.get("id") or "")
        score = score_map.get(model_id)
        if score is None or score.profile != profile:
            score = seed_role_score(model, profile)
        if score.routine_eligible:
            ranked.append(score)
    ranked.sort(
        key=lambda item: (
            -item.quality_score,
            -item.reliability_score,
            -(item.speed_score if item.speed_score is not None else MIN_ROUTINE_OUTPUT_TPS),
            item.model_id,
        )
    )
    return ranked[: max(0, limit)]


def can_admit_task(
    usage: ConcurrencyUsage,
    *,
    writer: bool = False,
    local_heavy: bool = False,
) -> bool:
    """Apply total, writer, and local-heavy ceilings as overlapping limits."""

    return (
        usage.total + 1 <= MAX_ACTIVE_SUBAGENTS
        and usage.writers + int(writer) <= MAX_ACTIVE_WRITERS
        and usage.local_heavy + int(local_heavy) <= MAX_RESIDENT_LOCAL_TASKS
    )


def _routing_state_path(root: Path | str) -> Path:
    return Path(root) / ".devflow" / "model-catalog" / "routing-state.json"


def save_role_scores(
    root: Path | str,
    scores: Mapping[tuple[str, str], ModelRoleScore],
) -> Path:
    """Atomically persist role scores and human-owned quarantine state."""

    path = _routing_state_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "scores": [
            asdict(score)
            for _, score in sorted(scores.items(), key=lambda item: item[0])
        ],
    }
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)
    return path


def load_role_scores(root: Path | str) -> dict[tuple[str, str], ModelRoleScore]:
    """Load persisted role scores, ignoring malformed individual records."""

    path = _routing_state_path(root)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return {}
    raw_scores = payload.get("scores") if isinstance(payload, dict) else None
    if not isinstance(raw_scores, list):
        return {}
    scores: dict[tuple[str, str], ModelRoleScore] = {}
    for raw in raw_scores:
        if not isinstance(raw, dict):
            continue
        try:
            score = ModelRoleScore(**raw)
        except (TypeError, ValueError):
            continue
        if score.model_id and score.profile:
            scores[(score.model_id, score.profile)] = score
    return scores


@contextmanager
def _routing_state_lock(root: Path | str):
    path = _routing_state_path(root).with_suffix(".lock")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def record_persisted_role_outcome(
    root: Path | str,
    *,
    model_id: str,
    role: str,
    success: bool | None = None,
    quality: float | None = None,
    human_score: float | None = None,
    fault_kind: str = "",
    output_tokens_per_second: float | None = None,
) -> ModelRoleScore | None:
    """Atomically merge one real execution outcome into its catalog scorecard."""

    profile = ROLE_PROFILE_MAP.get(role)
    if profile is None or not model_id:
        return None
    from devflow.loop.model_catalog import load_free_cloud_catalog

    catalog = load_free_cloud_catalog(root)
    raw_models = catalog.get("models") if isinstance(catalog, dict) else None
    models = raw_models if isinstance(raw_models, list) else []
    model = next(
        (
            entry
            for entry in models
            if isinstance(entry, dict) and entry.get("id") == model_id
        ),
        None,
    )
    if model is None:
        return None
    eligible_profiles = model.get("eligible_profiles")
    if not isinstance(eligible_profiles, list) or profile not in eligible_profiles:
        return None
    with _routing_state_lock(root):
        scores = load_role_scores(root)
        key = (model_id, profile)
        score = scores.get(key) or seed_role_score(model, profile)
        updated = record_role_outcome(
            score,
            quality=quality,
            human_score=human_score,
            success=success,
            fault_kind=fault_kind,
            output_tokens_per_second=output_tokens_per_second,
        )
        scores[key] = updated
        save_role_scores(root, scores)
    return updated


def record_run_human_feedback(
    root: Path | str,
    *,
    run_id: str,
    decision_id: str,
    decision: str,
) -> int:
    """Apply one idempotent human decision to free-cloud contributors."""

    normalized = decision.strip().lower()
    feedback_decision = (
        "accept"
        if normalized in {"accept", "complete"}
        else "reject"
        if normalized == "block"
        else "correction"
    )
    from devflow.loop.model_catalog import load_free_cloud_catalog
    from devflow.loop.pipeline_run import load_pipeline_run

    catalog = load_free_cloud_catalog(root)
    raw_models = catalog.get("models") if isinstance(catalog, dict) else None
    models = {
        str(entry.get("id")): entry
        for entry in (raw_models if isinstance(raw_models, list) else [])
        if isinstance(entry, dict) and entry.get("id")
    }
    run_data = load_pipeline_run(root, run_id)
    feed = run_data.get("worker-feed.jsonl")
    entries = feed if isinstance(feed, list) else []
    contributors: set[tuple[str, str]] = set()
    for entry in entries:
        if not isinstance(entry, dict) or entry.get("event") != "completed":
            continue
        usage = entry.get("usage")
        actual_model = usage.get("actual_model") if isinstance(usage, dict) else None
        model_id = str(actual_model or entry.get("model") or "")
        profile = ROLE_PROFILE_MAP.get(str(entry.get("role") or ""))
        model = models.get(model_id)
        if model is None or profile is None:
            continue
        eligible = model.get("eligible_profiles")
        if isinstance(eligible, list) and profile in eligible:
            contributors.add((model_id, profile))

    event_key = f"{run_id}:{decision_id}"
    events_path = _routing_state_path(root).with_name("human-feedback-events.json")
    with _routing_state_lock(root):
        try:
            event_payload = json.loads(events_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            event_payload = {"applied": []}
        applied = event_payload.get("applied")
        applied_ids = set(applied if isinstance(applied, list) else [])
        if event_key in applied_ids:
            return 0
        scores = load_role_scores(root)
        for model_id, profile in sorted(contributors):
            model = models[model_id]
            key = (model_id, profile)
            score = scores.get(key) or seed_role_score(model, profile)
            scores[key] = record_human_role_feedback(
                score,
                decision=feedback_decision,
            )
        save_role_scores(root, scores)
        applied_ids.add(event_key)
        events_path.write_text(
            json.dumps({"applied": sorted(applied_ids)}, indent=2) + "\n",
            encoding="utf-8",
        )
    return len(contributors)


__all__ = [
    "MAX_ACTIVE_SUBAGENTS",
    "MAX_ACTIVE_WRITERS",
    "MAX_RESIDENT_LOCAL_TASKS",
    "MIN_ROUTINE_OUTPUT_TPS",
    "ROLE_PROFILE_MAP",
    "ConcurrencyUsage",
    "ModelRoleScore",
    "can_admit_task",
    "load_role_scores",
    "quarantine_role",
    "rank_free_cloud_models",
    "record_human_role_feedback",
    "record_persisted_role_outcome",
    "record_role_outcome",
    "record_run_human_feedback",
    "restore_role",
    "save_role_scores",
    "seed_role_score",
]
