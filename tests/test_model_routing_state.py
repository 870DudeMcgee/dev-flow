"""Tests for role-specific model scoring, health, and concurrency policy."""

from __future__ import annotations

import json

import pytest

from devflow.loop.model_routing_state import (
    ConcurrencyUsage,
    ModelRoleScore,
    can_admit_task,
    load_role_scores,
    quarantine_role,
    rank_free_cloud_models,
    record_human_role_feedback,
    record_persisted_role_outcome,
    record_role_outcome,
    record_run_human_feedback,
    restore_role,
    save_role_scores,
    seed_role_score,
)


def _catalog_model(
    model_id: str,
    *,
    profiles: list[str],
    reasoning: bool = True,
    tools: bool = True,
    structured: bool = True,
    long_context: bool = True,
) -> dict:
    return {
        "id": model_id,
        "eligible_profiles": profiles,
        "capabilities": {
            "coding": "builder" in profiles or "code-scout" in profiles,
            "image_input": "vision-research" in profiles,
            "long_context": long_context,
            "reasoning": reasoning,
            "structured_output": structured,
            "tool_calling": tools,
        },
        "cost_class": "free_cloud",
        "health": "healthy",
    }


def test_seeded_score_is_role_specific_and_advertised() -> None:
    model = _catalog_model("example/model:free", profiles=["builder", "research-scout"])

    builder = seed_role_score(model, "builder")
    research = seed_role_score(model, "research-scout")

    assert 0 <= builder.quality_score <= 100
    assert 0 <= research.quality_score <= 100
    assert builder.profile == "builder"
    assert builder.confidence == "advertised"
    assert builder.sample_count == 0
    assert builder.quality_score != research.quality_score


def test_real_outcomes_dominate_prior_after_five_tasks() -> None:
    score = ModelRoleScore(model_id="example/model:free", profile="builder", prior_score=80)

    for _ in range(4):
        score = record_role_outcome(score, quality=20, success=True)
    assert score.sample_count == 4
    assert score.quality_score > 40
    assert score.confidence == "provisional"

    score = record_role_outcome(score, quality=20, success=True)
    assert score.sample_count == 5
    assert score.quality_score < 40
    assert score.confidence == "medium"


def test_human_feedback_is_the_strongest_quality_signal() -> None:
    score = ModelRoleScore(model_id="example/model:free", profile="builder", prior_score=80)
    for _ in range(5):
        score = record_role_outcome(score, quality=85, success=True)

    corrected = record_role_outcome(score, human_score=10)

    assert corrected.human_feedback_count == 1
    assert corrected.quality_score < 40


def test_human_decision_counters_are_explicit() -> None:
    score = ModelRoleScore(model_id="example/model:free", profile="builder", prior_score=80)

    accepted = record_human_role_feedback(score, decision="accept")
    corrected = record_human_role_feedback(accepted, decision="correction")
    rejected = record_human_role_feedback(corrected, decision="reject")

    assert rejected.human_accept_count == 1
    assert rejected.human_correction_count == 1
    assert rejected.human_reject_count == 1
    assert rejected.human_feedback_count == 3


def test_infrastructure_failure_changes_reliability_not_quality() -> None:
    score = ModelRoleScore(model_id="example/model:free", profile="research-scout", prior_score=75)

    failed = record_role_outcome(
        score,
        success=False,
        fault_kind="provider_rate_limit",
    )

    assert failed.quality_score == score.quality_score
    assert failed.sample_count == 0
    assert failed.reliability_score < score.reliability_score


def test_repeated_speed_samples_enforce_five_token_floor() -> None:
    score = ModelRoleScore(model_id="example/model:free", profile="builder", prior_score=70)
    score = record_role_outcome(score, output_tokens_per_second=4.0)
    score = record_role_outcome(score, output_tokens_per_second=4.5)
    assert score.routine_eligible is True

    score = record_role_outcome(score, output_tokens_per_second=3.5)
    assert score.speed_sample_count == 3
    assert score.speed_score == 4.0
    assert score.routine_eligible is False


def test_quarantine_restoration_requires_human_approval() -> None:
    score = ModelRoleScore(model_id="example/model:free", profile="builder", prior_score=70)
    quarantined = quarantine_role(score, reason="malformed tool calls")

    assert quarantined.health == "quarantined"
    assert quarantined.routine_eligible is False
    with pytest.raises(ValueError, match="human approval"):
        restore_role(quarantined, human_approved=False)

    restored = restore_role(quarantined, human_approved=True)
    assert restored.health == "healthy"
    assert restored.routine_eligible is True


def test_ranking_uses_capability_health_quality_and_three_model_limit() -> None:
    models = [
        _catalog_model(f"example/model-{index}:free", profiles=["builder"])
        for index in range(5)
    ]
    scores = {
        model["id"]: ModelRoleScore(
            model_id=model["id"],
            profile="builder",
            prior_score=score,
        )
        for model, score in zip(models, (60, 95, 80, 75, 70), strict=True)
    }
    scores["example/model-1:free"] = quarantine_role(
        scores["example/model-1:free"],
        reason="human review required",
    )

    ranked = rank_free_cloud_models(models, "builder", scores=scores, limit=3)

    assert [entry.model_id for entry in ranked] == [
        "example/model-2:free",
        "example/model-3:free",
        "example/model-4:free",
    ]


def test_concurrency_ceilings_overlap_instead_of_reserving_slots() -> None:
    assert can_admit_task(ConcurrencyUsage(total=7, writers=3, local_heavy=2), writer=True, local_heavy=True)
    assert not can_admit_task(ConcurrencyUsage(total=8, writers=2, local_heavy=0))
    assert not can_admit_task(ConcurrencyUsage(total=3, writers=4, local_heavy=0), writer=True)
    assert not can_admit_task(ConcurrencyUsage(total=3, writers=1, local_heavy=3), local_heavy=True)
    assert can_admit_task(ConcurrencyUsage(total=7, writers=4, local_heavy=0), writer=False)


def test_role_scores_and_quarantine_state_round_trip(tmp_path) -> None:
    score = ModelRoleScore(model_id="example/model:free", profile="builder", prior_score=75)
    score = record_role_outcome(score, quality=90, success=True, output_tokens_per_second=18)
    score = quarantine_role(score, reason="human review required")

    state_path = save_role_scores(tmp_path, {("example/model:free", "builder"): score})
    loaded = load_role_scores(tmp_path)

    assert state_path == tmp_path / ".devflow" / "model-catalog" / "routing-state.json"
    assert loaded == {("example/model:free", "builder"): score}


def test_runtime_outcome_updates_persisted_reliability_and_speed(tmp_path) -> None:
    catalog_path = tmp_path / ".devflow" / "model-catalog" / "current.json"
    catalog_path.parent.mkdir(parents=True)
    catalog_path.write_text(
        json.dumps({
            "models": [
                _catalog_model("example/model:free", profiles=["builder"]),
            ]
        }),
        encoding="utf-8",
    )

    updated = record_persisted_role_outcome(
        tmp_path,
        model_id="example/model:free",
        role="builder",
        success=True,
        output_tokens_per_second=12.5,
    )

    assert updated is not None
    assert updated.success_count == 1
    assert updated.speed_score == 12.5
    assert load_role_scores(tmp_path)[("example/model:free", "builder")] == updated


def test_run_human_feedback_is_persisted_once_per_decision(tmp_path) -> None:
    from devflow.loop.pipeline_run import append_worker_feed_entry, create_pipeline_run

    catalog_path = tmp_path / ".devflow" / "model-catalog" / "current.json"
    catalog_path.parent.mkdir(parents=True)
    catalog_path.write_text(
        json.dumps({
            "models": [
                _catalog_model("example/model:free", profiles=["builder"]),
            ]
        }),
        encoding="utf-8",
    )
    run_id = create_pipeline_run(tmp_path, {"title": "t", "description": "d"})
    append_worker_feed_entry(tmp_path, run_id, {
        "event": "completed",
        "role": "builder",
        "model": "example/model:free",
        "usage": {"actual_model": "example/model:free"},
    })

    first = record_run_human_feedback(
        tmp_path,
        run_id=run_id,
        decision_id="decision-1",
        decision="accept",
    )
    replay = record_run_human_feedback(
        tmp_path,
        run_id=run_id,
        decision_id="decision-1",
        decision="accept",
    )

    score = load_role_scores(tmp_path)[("example/model:free", "builder")]
    assert first == 1
    assert replay == 0
    assert score.human_accept_count == 1
    assert score.human_feedback_count == 1
