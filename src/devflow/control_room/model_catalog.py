"""Read projection and bounded operator controls for the shared model catalog."""

from __future__ import annotations

from pathlib import Path

from devflow.loop.model_catalog import load_free_cloud_catalog
from devflow.loop.model_routing_state import (
    MAX_ACTIVE_SUBAGENTS,
    MAX_ACTIVE_WRITERS,
    MAX_RESIDENT_LOCAL_TASKS,
    ModelRoleScore,
    load_role_scores,
    quarantine_role,
    rank_free_cloud_models,
    restore_role,
    save_role_scores,
    seed_role_score,
)


WORKER_PROFILES = (
    "research-scout",
    "code-scout",
    "builder",
    "judge-reviewer",
    "planning-specification",
    "vision-research",
    "classifier-safety",
)


def _catalog_models(catalog: dict) -> list[dict]:
    models = catalog.get("models")
    return [model for model in models if isinstance(model, dict)] if isinstance(models, list) else []


def _score_payload(score: ModelRoleScore) -> dict:
    return {
        "model_id": score.model_id,
        "profile": score.profile,
        "quality_score": score.quality_score,
        "reliability_score": score.reliability_score,
        "speed_score": score.speed_score,
        "confidence": score.confidence,
        "sample_count": score.sample_count,
        "human_feedback_count": score.human_feedback_count,
        "health": score.health,
        "routine_eligible": score.routine_eligible,
    }


def model_catalog_snapshot(root: Path | str) -> dict:
    """Project the shared catalog and role state for the DevFlow control room."""

    catalog = load_free_cloud_catalog(root)
    models = _catalog_models(catalog)
    persisted = load_role_scores(root)
    profiles: dict[str, list[dict]] = {}
    for profile in WORKER_PROFILES:
        profile_scores = {
            model_id: score
            for (model_id, saved_profile), score in persisted.items()
            if saved_profile == profile
        }
        profiles[profile] = [
            _score_payload(score)
            for score in rank_free_cloud_models(
                models,
                profile,
                scores=profile_scores,
                limit=3,
            )
        ]

    capability_names = (
        "coding",
        "image_input",
        "reasoning",
        "structured_output",
        "tool_calling",
    )
    capability_counts = {
        capability: sum(
            1
            for model in models
            if isinstance(model.get("capabilities"), dict)
            and model["capabilities"].get(capability) is True
        )
        for capability in capability_names
    }
    quarantined_roles = [
        {
            "model_id": score.model_id,
            "profile": score.profile,
            "reason": score.quarantine_reason,
        }
        for score in persisted.values()
        if score.health == "quarantined"
    ]
    quarantined_roles.sort(key=lambda entry: (entry["model_id"], entry["profile"]))

    return {
        "status": "ready" if models else "missing",
        "provider": catalog.get("provider") or "openrouter",
        "fetched_at": catalog.get("fetched_at"),
        "model_count": len(models),
        "capability_counts": capability_counts,
        "limits": {
            "total": MAX_ACTIVE_SUBAGENTS,
            "writers": MAX_ACTIVE_WRITERS,
            "local_heavy": MAX_RESIDENT_LOCAL_TASKS,
        },
        "profiles": profiles,
        "quarantined_roles": quarantined_roles,
    }


def change_model_role_health(
    root: Path | str,
    *,
    model_id: str,
    profile: str,
    action: str,
    reason: str = "",
    human_approved: bool,
) -> dict:
    """Apply an explicit operator quarantine or restoration decision."""

    catalog = load_free_cloud_catalog(root)
    model = next(
        (entry for entry in _catalog_models(catalog) if entry.get("id") == model_id),
        None,
    )
    if model is None:
        raise ValueError(f"Unknown catalog model: {model_id}")
    eligible_profiles = model.get("eligible_profiles")
    if not isinstance(eligible_profiles, list) or profile not in eligible_profiles:
        raise ValueError(f"Model {model_id} is not eligible for profile {profile}.")

    scores = load_role_scores(root)
    key = (model_id, profile)
    score = scores.get(key) or seed_role_score(model, profile)
    if action == "quarantine":
        if not reason.strip():
            raise ValueError("Quarantine requires a reason.")
        score = quarantine_role(score, reason=reason)
    elif action == "restore":
        score = restore_role(score, human_approved=human_approved)
    else:
        raise ValueError(f"Unknown model health action: {action}")
    scores[key] = score
    save_role_scores(root, scores)
    return _score_payload(score)


__all__ = [
    "WORKER_PROFILES",
    "change_model_role_health",
    "model_catalog_snapshot",
]
