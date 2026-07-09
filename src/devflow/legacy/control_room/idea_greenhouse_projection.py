from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from devflow.legacy.control_room.idea_foundry import IdeaFoundryError, greenhouse_lane_for_idea, list_ideas
from devflow.legacy.control_room.log_sanitizer import sanitize_log_line
from devflow.legacy.control_room.supervisor_surface import classify_supervisor_command


IDEA_LANE_ORDER = ["raw", "clarify", "candidate", "promoted", "parked", "archived"]
IDEA_LANE_LABELS = {
    "raw": "Raw",
    "clarify": "Clarify",
    "candidate": "Candidate",
    "promoted": "Promoted",
    "parked": "Parked",
    "archived": "Archived",
}
IDEA_LANE_TONES = {
    "raw": "muted",
    "clarify": "purple",
    "candidate": "blue",
    "promoted": "green",
    "parked": "slate",
    "archived": "dark",
}
IDEA_LANE_CARD_LIMIT = 5


class OperatingLayerIdeaAction(BaseModel):
    label: str
    command: str | None = None
    safety_class: str = "read_only"
    requires_human_approval: bool = False


class OperatingLayerIdeaCard(BaseModel):
    id: str
    title: str
    lane: str
    status: str
    maturity: str
    tags: list[str] = Field(default_factory=list)
    source: str | None = None
    updated_at: str | None = None
    summary: str = ""
    evidence_paths: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    primary_action: OperatingLayerIdeaAction | None = None


class OperatingLayerIdeaLane(BaseModel):
    id: str
    label: str
    tone: str
    count: int
    cards: list[OperatingLayerIdeaCard] = Field(default_factory=list)


class OperatingLayerIdeaGreenhouse(BaseModel):
    headline: str
    counts: dict[str, int] = Field(default_factory=dict)
    lanes: list[OperatingLayerIdeaLane] = Field(default_factory=list)
    primary_next_action: OperatingLayerIdeaAction | None = None


def build_idea_greenhouse(root: Path, warnings: list[str]) -> OperatingLayerIdeaGreenhouse:
    counts = {lane_id: 0 for lane_id in IDEA_LANE_ORDER}
    cards_by_lane: dict[str, list[OperatingLayerIdeaCard]] = {lane_id: [] for lane_id in IDEA_LANE_ORDER}
    try:
        items = list_ideas(root)
    except IdeaFoundryError as exc:
        warnings.append(f"idea greenhouse unavailable: {exc}")
        return _empty_idea_greenhouse()
    except Exception as exc:  # pragma: no cover - defensive projection boundary
        warnings.append(f"idea greenhouse unavailable: {exc}")
        return _empty_idea_greenhouse()

    for item in sorted(items, key=_idea_recent_sort_key, reverse=True):
        try:
            lane_id = greenhouse_lane_for_idea(item)
            if lane_id not in counts:
                lane_id = "raw"
            card = _idea_card(item, lane_id)
        except Exception as exc:
            idea_id = str(item.get("id") or "unknown") if isinstance(item, dict) else "unknown"
            warnings.append(f"idea greenhouse skipped malformed idea {idea_id}: {exc}")
            continue
        counts[lane_id] += 1
        if len(cards_by_lane[lane_id]) < IDEA_LANE_CARD_LIMIT:
            cards_by_lane[lane_id].append(card)

    lanes = [
        OperatingLayerIdeaLane(
            id=lane_id,
            label=IDEA_LANE_LABELS[lane_id],
            tone=IDEA_LANE_TONES[lane_id],
            count=counts[lane_id],
            cards=cards_by_lane[lane_id],
        )
        for lane_id in IDEA_LANE_ORDER
    ]
    return OperatingLayerIdeaGreenhouse(
        headline=_idea_greenhouse_headline(sum(counts.values())),
        counts=counts,
        lanes=lanes,
        primary_next_action=_idea_greenhouse_primary_action(lanes),
    )


def _empty_idea_greenhouse() -> OperatingLayerIdeaGreenhouse:
    return OperatingLayerIdeaGreenhouse(
        headline="No captured ideas yet",
        counts={lane_id: 0 for lane_id in IDEA_LANE_ORDER},
        lanes=[
            OperatingLayerIdeaLane(
                id=lane_id,
                label=IDEA_LANE_LABELS[lane_id],
                tone=IDEA_LANE_TONES[lane_id],
                count=0,
                cards=[],
            )
            for lane_id in IDEA_LANE_ORDER
        ],
        primary_next_action=_idea_hint_action(
            "Capture idea",
            'devflow idea capture "<idea>" --source operating-layer',
        ),
    )


def _idea_card(metadata: dict[str, Any], lane_id: str) -> OperatingLayerIdeaCard:
    idea_id = str(metadata.get("id") or "").strip()
    if not idea_id:
        raise ValueError("missing idea id")
    return OperatingLayerIdeaCard(
        id=idea_id,
        title=_idea_title(metadata),
        lane=lane_id,
        status=str(metadata.get("status") or "unknown"),
        maturity=str(metadata.get("maturity") or "unknown"),
        tags=_idea_tags(metadata),
        source=str(metadata.get("source")) if metadata.get("source") is not None else None,
        updated_at=_idea_timestamp(metadata, "updated_at") or _idea_timestamp(metadata, "created_at"),
        summary=_idea_summary(metadata, lane_id),
        evidence_paths=_idea_evidence_paths(metadata),
        metadata=_idea_detail_metadata(metadata, lane_id),
        primary_action=_idea_primary_action(metadata, lane_id),
    )


def _idea_evidence_paths(metadata: dict[str, Any]) -> list[str]:
    idea_id = str(metadata.get("id") or "").strip()
    paths = [f".devflow/ideas/{idea_id}/idea.json"] if idea_id else []
    for key in (
        "raw_path",
        "classification_path",
        "promotion_path",
        "created_goal_path",
        "created_task_path",
        "latest_brainstorm_session_path",
    ):
        value = str(metadata.get(key) or "").strip()
        if value:
            paths.append(value)
    brainstorm_paths = metadata.get("brainstorm_session_paths")
    if isinstance(brainstorm_paths, list):
        for value in brainstorm_paths:
            path = str(value or "").strip()
            if path:
                paths.append(path)
    if idea_id:
        paths.append(f".devflow/ideas/{idea_id}/events.jsonl")
    deduped: list[str] = []
    for path in paths:
        if path not in deduped:
            deduped.append(path)
    return deduped


def _idea_detail_metadata(metadata: dict[str, Any], lane_id: str) -> dict[str, Any]:
    payload = json.loads(json.dumps(metadata, default=str))
    payload["greenhouse_lane"] = lane_id
    payload["evidence_paths"] = _idea_evidence_paths(metadata)
    payload["lineage"] = _idea_lineage(metadata)
    return payload


def _idea_lineage(metadata: dict[str, Any]) -> dict[str, Any]:
    idea_id = str(metadata.get("id") or "").strip()
    lineage: dict[str, Any] = {
        "schema_version": 1,
        "source_idea_id": idea_id,
        "idea_path": f".devflow/ideas/{idea_id}" if idea_id else None,
    }
    latest_session = str(metadata.get("latest_brainstorm_session_id") or "").strip()
    latest_path = str(metadata.get("latest_brainstorm_session_path") or "").strip()
    if latest_session:
        lineage["latest_brainstorm_session_id"] = latest_session
    if latest_path:
        lineage["latest_brainstorm_session_path"] = latest_path
    sessions = metadata.get("brainstorm_session_ids")
    if isinstance(sessions, list) and sessions:
        lineage["brainstorm_session_ids"] = [str(item) for item in sessions if str(item).strip()]
    return {key: value for key, value in lineage.items() if value}


def _idea_primary_action(metadata: dict[str, Any], lane_id: str) -> OperatingLayerIdeaAction:
    idea_id = str(metadata["id"])
    maturity = str(metadata.get("maturity") or "")
    promotion_target = str(metadata.get("promotion_target") or "")
    if lane_id == "raw":
        return _idea_hint_action(
            "Classify raw idea",
            f'devflow idea classify {idea_id} --maturity concept --note "<note>"',
        )
    if lane_id == "clarify":
        return _idea_hint_action(
            "Clarify idea",
            f'devflow idea classify {idea_id} --maturity candidate --note "<note>"',
        )
    if lane_id == "candidate" and maturity == "goal_ready":
        return _idea_hint_action(
            "Promote to goal",
            f'devflow idea promote {idea_id} --to goal --rationale "<rationale>"',
        )
    if lane_id == "candidate" and maturity == "task_ready":
        return _idea_hint_action(
            "Promote to task",
            f'devflow idea promote {idea_id} --to task --rationale "<rationale>"',
        )
    if lane_id == "candidate":
        return _idea_hint_action(
            "Promote readiness",
            f'devflow idea classify {idea_id} --maturity task_ready --note "<note>"',
        )
    if lane_id == "promoted" and promotion_target == "goal":
        return _idea_concrete_action("Preview goal creation", f"devflow idea create-goal {idea_id} --dry-run")
    if lane_id == "promoted" and promotion_target == "task":
        return _idea_concrete_action("Preview task creation", f"devflow idea create-task {idea_id} --dry-run")
    if lane_id == "promoted":
        return _idea_concrete_action("Inspect promoted idea", f"devflow idea show {idea_id}")
    if lane_id == "parked":
        return _idea_concrete_action("Inspect parked idea", f"devflow idea show {idea_id}")
    if lane_id == "archived":
        return _idea_concrete_action("Inspect archived idea", f"devflow idea show {idea_id}")
    return _idea_concrete_action("Inspect idea", f"devflow idea show {idea_id}")


def _idea_hint_action(label: str, command: str) -> OperatingLayerIdeaAction:
    return OperatingLayerIdeaAction(
        label=label,
        command=command,
        safety_class="requires_input",
        requires_human_approval=False,
    )


def _idea_concrete_action(label: str, command: str) -> OperatingLayerIdeaAction:
    classification = classify_supervisor_command(command)
    return OperatingLayerIdeaAction(
        label=label,
        command=command,
        safety_class=str(classification["safety_class"]),
        requires_human_approval=bool(classification["requires_human_approval"]),
    )


def _idea_greenhouse_primary_action(
    lanes: list[OperatingLayerIdeaLane],
) -> OperatingLayerIdeaAction:
    for lane_id in IDEA_LANE_ORDER:
        lane = next((candidate for candidate in lanes if candidate.id == lane_id), None)
        if lane and lane.cards and lane.cards[0].primary_action:
            return lane.cards[0].primary_action
    return _idea_hint_action("Capture idea", 'devflow idea capture "<idea>" --source operating-layer')


def _idea_greenhouse_headline(total: int) -> str:
    if total == 0:
        return "No captured ideas yet"
    return f"{total} idea{'s' if total != 1 else ''} in greenhouse"


def _idea_title(metadata: dict[str, Any]) -> str:
    title = str(metadata.get("title") or "").strip()
    return sanitize_log_line(title, max_chars=96) if title else str(metadata.get("id") or "Untitled idea")


def _idea_tags(metadata: dict[str, Any]) -> list[str]:
    tags = metadata.get("tags")
    if not isinstance(tags, list):
        return []
    return [tag for tag in (str(tag).strip() for tag in tags) if tag]


def _idea_summary(metadata: dict[str, Any], lane_id: str) -> str:
    if lane_id == "parked":
        reason = str(metadata.get("park_reason") or "").strip()
        return sanitize_log_line(f"Parked: {reason}", max_chars=140) if reason else "Parked for later."
    if lane_id == "promoted":
        target = str(metadata.get("promotion_target") or "").strip()
        if target:
            created_id = metadata.get("created_goal_id") if target == "goal" else metadata.get("created_task_id")
            if created_id:
                return sanitize_log_line(f"Promoted to {target}; created {created_id}.", max_chars=140)
            return f"Promoted to {target}; creation is still explicit."
        return "Promotion decision recorded."
    source = str(metadata.get("source") or "").strip()
    tags = _idea_tags(metadata)
    parts = [str(metadata.get("maturity") or "unknown")]
    if source:
        parts.append(f"source: {source}")
    if tags:
        parts.append("tags: " + ", ".join(tags[:3]))
    return sanitize_log_line(" | ".join(parts), max_chars=140)


def _idea_timestamp(metadata: dict[str, Any], key: str) -> str | None:
    value = metadata.get(key)
    return str(value) if value else None


def _idea_recent_sort_key(metadata: dict[str, Any]) -> str:
    return _idea_timestamp(metadata, "updated_at") or _idea_timestamp(metadata, "created_at") or ""
