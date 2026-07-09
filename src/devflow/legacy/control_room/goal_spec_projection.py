from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from devflow.legacy.control_room.browser_task_capabilities import build_browser_task_capability, intent_for_command, scope_task_command
from devflow.legacy.control_room.freshness import FreshnessReport
from devflow.legacy.control_room.paths import goals_dir, relative_path


class OperatingLayerAction(BaseModel):
    label: str
    command: str
    scope: str
    safety_class: str
    requires_human_approval: bool
    supervisor_may_auto_run: bool
    intent: str | None = None
    required_inputs: list[str] = Field(default_factory=list)
    reason: str | None = None


class OperatingLayerSpecSlice(BaseModel):
    slice_id: str
    title: str
    state: str
    risk: str | None = None
    execution_mode: str | None = None
    parallel_safe: bool | None = None
    linked_task_ids: list[str] = Field(default_factory=list)


class OperatingLayerSpecReference(BaseModel):
    path: str
    kind: str
    title: str
    source: str
    status: str


class OperatingLayerSpecBoardGoal(BaseModel):
    goal_id: str
    title: str
    state: str
    spec_path: str
    slice_count: int
    slices: list[OperatingLayerSpecSlice] = Field(default_factory=list)
    references: list[OperatingLayerSpecReference] = Field(default_factory=list)


class OperatingLayerGoalBoardLane(BaseModel):
    slice_id: str
    title: str
    lane_state: str
    recommendation: str
    command: str | None = None
    actions: list[OperatingLayerAction] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    shared_files: list[str] = Field(default_factory=list)
    linked_task_ids: list[str] = Field(default_factory=list)
    parallel_safe: bool
    risk: str
    execution_mode: str


class OperatingLayerGoalBoardBatch(BaseModel):
    batch_id: str
    kind: str
    lane_ids: list[str] = Field(default_factory=list)
    task_ids: list[str] = Field(default_factory=list)
    command_count: int
    commands: list[str] = Field(default_factory=list)
    actions: list[OperatingLayerAction] = Field(default_factory=list)
    shared_files: list[str] = Field(default_factory=list)
    verification_scope: str | None = None
    reason: str


class OperatingLayerGoalBoardGoal(BaseModel):
    goal_id: str
    title: str
    goal_state: str
    lifecycle: str = "missing"
    lifecycle_reason: str = ""
    loop_state: str
    total_slices: int
    completed_slice_count: int
    active_task_count: int
    blocked_lane_count: int
    ready_parallel_lane_count: int
    ready_parallel_batch_count: int
    ready_worker_batch_count: int
    ready_verification_batch_count: int
    next_action: str
    actions: list[OperatingLayerAction] = Field(default_factory=list)
    lanes: list[OperatingLayerGoalBoardLane] = Field(default_factory=list)
    blocked_lanes: list[OperatingLayerGoalBoardLane] = Field(default_factory=list)
    ready_lanes: list[OperatingLayerGoalBoardLane] = Field(default_factory=list)
    parallel_batches: list[OperatingLayerGoalBoardBatch] = Field(default_factory=list)
    worker_batches: list[OperatingLayerGoalBoardBatch] = Field(default_factory=list)
    verification_batches: list[OperatingLayerGoalBoardBatch] = Field(default_factory=list)


def build_operating_layer_action(label: str, command: str, scope: str) -> OperatingLayerAction:
    capability = build_browser_task_capability(intent_for_command(command), label, command, scope=scope)
    return OperatingLayerAction(
        label=capability.label,
        command=capability.command,
        scope=capability.scope,
        safety_class=capability.safety_class,
        requires_human_approval=capability.requires_human_approval,
        supervisor_may_auto_run=capability.supervisor_may_auto_run,
        intent=capability.intent,
        required_inputs=capability.required_inputs,
        reason=capability.reason,
    )


def build_goal_board(
    root: Path,
    freshness: FreshnessReport | None,
    *,
    project_id: str | None,
    warnings: list[str] | None = None,
) -> list[OperatingLayerGoalBoardGoal]:
    if not freshness:
        return []
    goals: list[OperatingLayerGoalBoardGoal] = []
    for goal in freshness.goal_loop:
        lifecycle, lifecycle_reason = _goal_board_lifecycle(
            root,
            goal.goal_id,
            fallback=goal.goal_state,
            warnings=warnings,
        )
        goals.append(
            OperatingLayerGoalBoardGoal(
                goal_id=goal.goal_id,
                title=goal.title,
                goal_state=goal.goal_state,
                lifecycle=lifecycle,
                lifecycle_reason=lifecycle_reason,
                loop_state=goal.loop_state,
                total_slices=goal.total_slices,
                completed_slice_count=goal.completed_slice_count,
                active_task_count=goal.active_task_count,
                blocked_lane_count=goal.blocked_lane_count,
                ready_parallel_lane_count=goal.ready_parallel_lane_count,
                ready_parallel_batch_count=goal.ready_parallel_batch_count,
                ready_worker_batch_count=goal.ready_worker_batch_count,
                ready_verification_batch_count=goal.ready_verification_batch_count,
                next_action=_safe_goal_command(root, goal.next_action, project_id),
                actions=_goal_actions(root, goal.goal_id, goal.next_action, project_id=project_id),
                lanes=[_goal_board_lane(root, lane, project_id=project_id) for lane in goal.lanes],
                blocked_lanes=[
                    _goal_board_lane(root, lane, project_id=project_id)
                    for lane in goal.lanes
                    if lane.lane_state in {"blocked", "needs_human_review"}
                ],
                ready_lanes=[
                    _goal_board_lane(root, lane, project_id=project_id)
                    for lane in goal.lanes
                    if lane.lane_state in {"ready_to_create_task", "ready_to_run_or_verify", "repair_or_verify", "ready_to_promote"}
                ],
                parallel_batches=[
                    _goal_board_batch(root, "parallel", batch, project_id=project_id)
                    for batch in goal.parallel_batches
                ],
                worker_batches=[
                    _goal_board_batch(root, "worker", batch, project_id=project_id)
                    for batch in goal.worker_batches
                ],
                verification_batches=[
                    _goal_board_batch(root, "verification", batch, project_id=project_id)
                    for batch in goal.verification_batches
                ],
            )
        )
    return goals


def build_spec_board(
    root: Path,
    freshness: FreshnessReport | None,
    *,
    warnings: list[str] | None = None,
) -> list[OperatingLayerSpecBoardGoal]:
    title_by_goal = {goal.goal_id: goal.title for goal in freshness.goal_loop} if freshness else {}
    state_by_goal = {goal.goal_id: goal.loop_state for goal in freshness.goal_loop} if freshness else {}
    board: list[OperatingLayerSpecBoardGoal] = []
    base = goals_dir(root)
    if not base.exists():
        return board
    for goal_path in sorted(path for path in base.iterdir() if path.is_dir()):
        goal_id = goal_path.name
        slices = _goal_slices(root, goal_path, warnings)
        board.append(
            OperatingLayerSpecBoardGoal(
                goal_id=goal_id,
                title=title_by_goal.get(goal_id) or _goal_title(goal_path, goal_id),
                state=state_by_goal.get(goal_id) or "unknown",
                spec_path=relative_path(root, goal_path),
                slice_count=len(slices),
                slices=slices,
                references=_spec_references(root, goal_path, warnings),
            )
        )
    return board


def _goal_board_lifecycle(
    root: Path,
    goal_id: str,
    *,
    fallback: str,
    warnings: list[str] | None = None,
) -> tuple[str, str]:
    try:
        from devflow.legacy.control_room.goal_projection import build_goal_status_projection

        projection = build_goal_status_projection(root, goal_id)
        return projection.lifecycle, projection.lifecycle_reason
    except Exception:
        if warnings is not None:
            goal_state_path = root / ".devflow" / "goals" / goal_id / "goal-state.yaml"
            _append_read_warning(warnings, root, goal_state_path, f"goal lifecycle projection failed for {goal_id}")
        if fallback in {"active", "paused", "blocked", "complete", "archived", "missing_lifecycle"}:
            return ("missing" if fallback == "missing_lifecycle" else fallback), ""
        return "unknown", ""


def _goal_board_lane(root: Path, lane: Any, *, project_id: str | None) -> OperatingLayerGoalBoardLane:
    return OperatingLayerGoalBoardLane(
        slice_id=lane.slice_id,
        title=lane.title,
        lane_state=lane.lane_state,
        recommendation=lane.recommendation,
        command=_safe_goal_command(root, lane.command, project_id),
        actions=_lane_actions(root, lane, project_id=project_id),
        blockers=list(lane.blockers),
        shared_files=list(lane.shared_files),
        linked_task_ids=list(lane.linked_task_ids),
        parallel_safe=lane.parallel_safe,
        risk=lane.risk,
        execution_mode=lane.execution_mode,
    )


def _goal_board_batch(root: Path, kind: str, batch: Any, *, project_id: str | None) -> OperatingLayerGoalBoardBatch:
    commands = [_safe_goal_command(root, command, project_id) for command in getattr(batch, "commands", [])]
    return OperatingLayerGoalBoardBatch(
        batch_id=batch.batch_id,
        kind=kind,
        lane_ids=list(batch.lane_ids),
        task_ids=list(getattr(batch, "task_ids", [])),
        command_count=len(commands),
        commands=commands,
        actions=[build_operating_layer_action(f"{kind.title()} command {index}", command, "goal") for index, command in enumerate(commands, start=1) if command],
        shared_files=list(batch.shared_files),
        verification_scope=getattr(batch, "verification_scope", None),
        reason=batch.reason,
    )


def _goal_actions(root: Path, goal_id: str, next_action: str | None, *, project_id: str | None) -> list[OperatingLayerAction]:
    commands = [
        ("Goal status", _safe_goal_command(root, f"devflow goal status {goal_id}", project_id)),
    ]
    if next_action and next_action.startswith("devflow "):
        commands.insert(0, ("Next goal action", _safe_goal_command(root, next_action, project_id)))
    return _deduped_actions(commands, "goal")


def _lane_actions(root: Path, lane: Any, *, project_id: str | None) -> list[OperatingLayerAction]:
    commands: list[tuple[str, str | None]] = []
    if lane.command:
        commands.append(("Lane recommendation", _safe_goal_command(root, lane.command, project_id)))
    for task_id in lane.linked_task_ids:
        commands.append(("Show linked task", scope_task_command(f"devflow task show {task_id}", project_id)))
    return _deduped_actions(commands, "goal")


def _deduped_actions(commands: list[tuple[str, str | None]], scope: str) -> list[OperatingLayerAction]:
    seen: set[str] = set()
    actions: list[OperatingLayerAction] = []
    for label, command in commands:
        if not command or command in seen:
            continue
        seen.add(command)
        actions.append(build_operating_layer_action(label, command, scope))
    return actions


def _safe_goal_command(root: Path, command: str | None, project_id: str | None) -> str | None:
    if not command:
        return None
    safe = _scrub_project_root(root, command)
    return scope_task_command(safe, project_id)


def _goal_title(goal_path: Path, fallback: str) -> str:
    goal_md = goal_path / "goal.md"
    if not goal_md.exists():
        return fallback
    for line in goal_md.read_text(encoding="utf-8").splitlines():
        stripped = line.strip("# ").strip()
        if stripped:
            return stripped[:120]
    return fallback


def _goal_slices(
    root: Path,
    goal_path: Path,
    warnings: list[str] | None = None,
) -> list[OperatingLayerSpecSlice]:
    path = goal_path / "task-slices.yaml"
    data = _read_yaml(
        path,
        warnings=warnings,
        root=root,
        label="task-slices.yaml",
    )
    if not data:
        return []
    raw_slices = data.get("task_slices") if isinstance(data, dict) else []
    if not isinstance(raw_slices, list):
        _append_read_warning(warnings, root, path, "task-slices.yaml task_slices must be a list")
        return []
    slices: list[OperatingLayerSpecSlice] = []
    for item in raw_slices:
        if not isinstance(item, dict):
            continue
        slice_id = str(item.get("task_id") or item.get("slice_id") or "unknown")
        linked = item.get("linked_task_ids") or item.get("linked_tasks") or []
        if isinstance(linked, str):
            linked = [linked]
        if not isinstance(linked, list):
            linked = []
        slices.append(
            OperatingLayerSpecSlice(
                slice_id=slice_id,
                title=str(item.get("title") or slice_id),
                state=_slice_state(item),
                risk=item.get("risk"),
                execution_mode=item.get("execution_mode"),
                parallel_safe=item.get("parallel_safe"),
                linked_task_ids=[str(value) for value in linked],
            )
        )
    return slices


def _spec_references(
    root: Path, goal_path: Path, warnings: list[str] | None = None
) -> list[OperatingLayerSpecReference]:
    references: list[OperatingLayerSpecReference] = []
    references.extend(_goal_context_references(root, goal_path))
    references.extend(_standards_index_references(root, warnings=warnings))
    references.extend(_architecture_contract_references(root))

    seen: set[str] = set()
    deduped: list[OperatingLayerSpecReference] = []
    for reference in references:
        key = f"{reference.kind}:{reference.path}"
        if key in seen:
            continue
        seen.add(key)
        deduped.append(reference)
    return deduped[:10]


def _goal_context_references(root: Path, goal_path: Path) -> list[OperatingLayerSpecReference]:
    path = goal_path / "context" / "relevant-files.md"
    if not path.exists():
        return []
    references: list[OperatingLayerSpecReference] = []
    for raw_target in _markdown_bullet_targets(path):
        target = _normalize_root_reference_path(root, raw_target)
        references.append(_spec_reference(root, target, "goal_reference", relative_path(root, path)))
    return references


def _standards_index_references(root: Path, warnings: list[str] | None = None) -> list[OperatingLayerSpecReference]:
    path = root / ".devflow" / "standards" / "index.yml"
    if not path.exists():
        path = root / ".devflow" / "standards" / "index.yaml"
    if not path.exists():
        path = root / ".devflow" / "standards" / "index.json"
    if not path.exists():
        return []
    data = _read_yaml(path, warnings=warnings, root=root, label=f"standards index ({relative_path(root, path)})")
    raw_items: Any = data.get("standards") or data.get("references") or data.get("items") or data
    if isinstance(raw_items, dict):
        raw_items = list(raw_items.values())
    if not isinstance(raw_items, list):
        _append_read_warning(warnings, root, path, "standards index entries must be a list")
        return []
    references: list[OperatingLayerSpecReference] = []
    for item in raw_items:
        if isinstance(item, str):
            target = _normalize_root_reference_path(root, item)
            references.append(_spec_reference(root, target, "standard", relative_path(root, path)))
            continue
        if not isinstance(item, dict):
            continue
        raw_target = item.get("path") or item.get("file") or item.get("href") or item.get("id")
        if not raw_target:
            continue
        target = _normalize_root_reference_path(root, str(raw_target))
        reference = _spec_reference(root, target, str(item.get("kind") or "standard"), relative_path(root, path))
        if item.get("title"):
            reference.title = str(item["title"])[:120]
        references.append(reference)
    return references


def _architecture_contract_references(root: Path) -> list[OperatingLayerSpecReference]:
    path = root / ".devflow" / "layers" / "architecture" / "contracts.md"
    if not path.exists():
        return []
    references: list[OperatingLayerSpecReference] = []
    for raw_target in _markdown_bullet_targets(path):
        target = _normalize_source_relative_reference_path(root, path.parent, raw_target)
        references.append(_spec_reference(root, target, "architecture_contract", relative_path(root, path)))
    return references


def _markdown_bullet_targets(path: Path) -> list[str]:
    targets: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped.startswith("- "):
            continue
        target = stripped[2:].strip()
        markdown_target = _markdown_link_target(target)
        if markdown_target:
            target = markdown_target
        target = target.strip().strip("`")
        if target:
            targets.append(target)
    return targets


def _markdown_link_target(value: str) -> str | None:
    start = value.find("](")
    if start == -1:
        return None
    end = value.find(")", start + 2)
    if end == -1:
        return None
    return value[start + 2 : end].strip()


def _normalize_root_reference_path(root: Path, value: str) -> str:
    if "://" in value:
        return value
    path = Path(value)
    if path.is_absolute():
        try:
            return relative_path(root, path)
        except ValueError:
            return _scrub_project_root(root, path.as_posix())
    return path.as_posix().removeprefix("./")


def _normalize_source_relative_reference_path(root: Path, source_dir: Path, value: str) -> str:
    if "://" in value:
        return value
    path = Path(value)
    if path.is_absolute():
        try:
            return relative_path(root, path)
        except ValueError:
            return _scrub_project_root(root, path.as_posix())
    return relative_path(root, (source_dir / path).resolve())


def _spec_reference(root: Path, path: str, kind: str, source: str) -> OperatingLayerSpecReference:
    return OperatingLayerSpecReference(
        path=path,
        kind=kind,
        title=_reference_title(root, path),
        source=source,
        status=_reference_status(root, path),
    )


def _reference_title(root: Path, path: str) -> str:
    if "://" in path:
        return path
    candidate = root / path
    if candidate.exists() and candidate.is_file() and candidate.suffix == ".md":
        for line in candidate.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                title = stripped.strip("# ").strip()
                if title:
                    return title[:120]
    return Path(path).name


def _reference_status(root: Path, path: str) -> str:
    if "://" in path:
        return "external"
    return "available" if (root / path).exists() else "missing"


def _slice_state(item: dict[str, Any]) -> str:
    if item.get("blocked_by"):
        return "blocked"
    if item.get("promotion_allowed") is True:
        return "ready_for_promotion"
    if item.get("parallel_safe") is True:
        return "parallel_candidate"
    return "planned"


def _read_yaml(
    path: Path,
    *,
    warnings: list[str] | None = None,
    root: Path | None = None,
    label: str | None = None,
) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:
        context = label or path.name
        _append_read_warning(warnings, root or path.parent, path, f"malformed {context}; failed to parse: {exc}")
        return {}
    if not isinstance(loaded, dict):
        context = label or path.name
        _append_read_warning(warnings, root or path.parent, path, f"{context} must be a mapping")
        return {}
    return loaded


def _append_read_warning(warnings: list[str] | None, root: Path, path: Path, detail: str) -> None:
    if warnings is None:
        return
    warning_path = _scrub_project_root(root, str(path))
    warnings.append(f"warning: {detail} at {warning_path}")


def _scrub_quarantined_checkout(value: str) -> str:
    return value.replace("/Users/jewelbait/Desktop/DevFlow", "<quarantined-devflow>")


def _scrub_project_root(root: Path, value: str) -> str:
    scrubbed = _scrub_quarantined_checkout(value)
    candidates = {root.as_posix(), root.resolve().as_posix()}
    for candidate in sorted(candidates, key=len, reverse=True):
        scrubbed = scrubbed.replace(candidate, "<repo-root>")
    return scrubbed
