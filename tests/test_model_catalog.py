"""Tests for the generated free-cloud model catalog."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from devflow.loop.model_catalog import (
    build_free_cloud_catalog,
    refresh_free_cloud_catalog,
)


FETCHED_AT = datetime(2026, 7, 13, 10, 0, tzinfo=timezone.utc)


def _model(
    model_id: str,
    *,
    name: str,
    description: str,
    prompt_price: str = "0",
    completion_price: str = "0",
    inputs: list[str] | None = None,
    outputs: list[str] | None = None,
    parameters: list[str] | None = None,
    context_length: int = 131_072,
) -> dict:
    return {
        "id": model_id,
        "name": name,
        "description": description,
        "context_length": context_length,
        "architecture": {
            "input_modalities": inputs or ["text"],
            "output_modalities": outputs or ["text"],
        },
        "pricing": {
            "prompt": prompt_price,
            "completion": completion_price,
        },
        "supported_parameters": parameters or [],
        "created": 1_783_000_000,
    }


def _payload() -> dict:
    return {
        "data": [
            _model(
                "example/code-agent:free",
                name="Example Code Agent (free)",
                description=(
                    "An agentic coding model optimized for software engineering, "
                    "repository work, and long-horizon reasoning."
                ),
                parameters=["tools", "tool_choice", "reasoning", "structured_outputs"],
                context_length=262_144,
            ),
            _model(
                "example/vision-reasoner:free",
                name="Example Vision Reasoner (free)",
                description="A multimodal reasoning model for visual research and analysis.",
                inputs=["text", "image"],
                parameters=["reasoning", "structured_outputs"],
            ),
            _model(
                "example/paid-code",
                name="Paid Code",
                description="Coding model.",
                prompt_price="0.000001",
                parameters=["tools"],
            ),
            _model(
                "example/image-generator:free",
                name="Image Generator (free)",
                description="Generates images.",
                outputs=["image"],
            ),
            _model(
                "example/music-generator:free",
                name="Music Generator (free)",
                description="Generates music from text prompts.",
                outputs=["text", "audio"],
            ),
        ]
    }


def test_build_catalog_filters_zero_price_text_chat_models() -> None:
    catalog = build_free_cloud_catalog(_payload(), fetched_at=FETCHED_AT)

    assert catalog["schema_version"] == 1
    assert catalog["fetched_at"] == "2026-07-13T10:00:00+00:00"
    assert catalog["model_count"] == 2
    assert [model["id"] for model in catalog["models"]] == [
        "example/code-agent:free",
        "example/vision-reasoner:free",
    ]


def test_catalog_uses_structured_metadata_and_advertised_strengths() -> None:
    catalog = build_free_cloud_catalog(_payload(), fetched_at=FETCHED_AT)
    code = catalog["models"][0]
    vision = catalog["models"][1]

    assert code["capabilities"] == {
        "coding": True,
        "image_input": False,
        "long_context": True,
        "reasoning": True,
        "structured_output": True,
        "tool_calling": True,
    }
    assert code["eligible_profiles"] == [
        "builder",
        "code-scout",
        "judge-reviewer",
        "planning-specification",
        "research-scout",
    ]
    assert code["eligibility"] == "immediate"
    assert code["confidence"] == "advertised"
    assert code["sample_count"] == 0
    assert "catalog_description" in code["evidence_sources"]
    assert "structured_api_metadata" in code["evidence_sources"]

    assert vision["capabilities"]["image_input"] is True
    assert vision["eligible_profiles"] == [
        "judge-reviewer",
        "planning-specification",
        "research-scout",
        "vision-research",
    ]


def test_refresh_persists_shared_snapshot_and_ignores_timestamp_only_changes(
    tmp_path: Path,
) -> None:
    first = refresh_free_cloud_catalog(
        tmp_path,
        fetch_catalog=lambda: _payload(),
        fetched_at=FETCHED_AT,
    )
    second = refresh_free_cloud_catalog(
        tmp_path,
        fetch_catalog=lambda: _payload(),
        fetched_at=datetime(2026, 7, 14, 10, 0, tzinfo=timezone.utc),
    )

    current_path = tmp_path / ".devflow" / "model-catalog" / "current.json"
    history_path = tmp_path / ".devflow" / "model-catalog" / "history" / "2026-07-13.json"
    assert first.changed is True
    assert first.added == ("example/code-agent:free", "example/vision-reasoner:free")
    assert second.changed is False
    assert second.added == ()
    assert second.removed == ()
    assert current_path.is_file()
    assert history_path.is_file()
    persisted = json.loads(current_path.read_text(encoding="utf-8"))
    assert persisted["model_count"] == 2
    assert persisted["models"][0]["first_seen"] == "2026-07-13T10:00:00+00:00"
    assert persisted["models"][0]["last_seen"] == "2026-07-14T10:00:00+00:00"


def test_refresh_reports_added_removed_and_changed_models(tmp_path: Path) -> None:
    refresh_free_cloud_catalog(
        tmp_path,
        fetch_catalog=lambda: _payload(),
        fetched_at=FETCHED_AT,
    )
    changed_payload = _payload()
    changed_payload["data"] = [
        {
            **changed_payload["data"][0],
            "context_length": 524_288,
        },
        _model(
            "example/new-researcher:free",
            name="New Researcher (free)",
            description="A research agent with search and reasoning strengths.",
            parameters=["tools", "reasoning"],
        ),
    ]

    result = refresh_free_cloud_catalog(
        tmp_path,
        fetch_catalog=lambda: changed_payload,
        fetched_at=datetime(2026, 7, 14, 10, 0, tzinfo=timezone.utc),
    )

    assert result.changed is True
    assert result.added == ("example/new-researcher:free",)
    assert result.removed == ("example/vision-reasoner:free",)
    assert result.modified == ("example/code-agent:free",)
