from __future__ import annotations

from pathlib import Path
from typing import Any

from devflow.control_room import builder_judge_loop
from devflow.control_room import builder_judge_runtime_registry as bj_runtime
from devflow.control_room.builder_judge_async_runtime import start_builder_judge_async_loop
from devflow.control_room.builder_judge_loop import (
    DEFAULT_BUILDER_PROFILE,
    DEFAULT_JUDGE_PROFILE,
    DEFAULT_MAX_ROUNDS,
    DEFAULT_PASS_THRESHOLD,
    BuilderJudgeConfig,
    BuilderJudgeConfigError,
    BuilderJudgeRunError,
    get_builder_judge_run,
    project_builder_judge_run,
    run_quality_gate,
)
from devflow.control_room.builder_judge_quality_gate import build_quality_gate_transcript_text
from devflow.control_room.project_registry import ProjectRegistryError, resolve_project_root

run_builder_judge_loop = builder_judge_loop.run_builder_judge_loop

BUILDER_JUDGE_START_VALIDATION_ERRORS = (
    BuilderJudgeConfigError,
    BuilderJudgeRunError,
    ProjectRegistryError,
    ValueError,
)
BUILDER_JUDGE_READ_BAD_REQUEST_ERRORS = (OSError, ValueError)
BUILDER_JUDGE_QUALITY_GATE_BAD_REQUEST_ERRORS = (
    BuilderJudgeConfigError,
    BuilderJudgeRunError,
    ProjectRegistryError,
    OSError,
    ValueError,
)


class BuilderJudgeRouteNotFound(ValueError):
    pass


def build_builder_judge_start_payload(repo_root: Path, payload: dict[str, object]) -> dict[str, Any]:
    root = _payload_project_root(repo_root, payload)
    definition_of_done = payload.get("definition_of_done")
    if not isinstance(definition_of_done, str) or not definition_of_done.strip():
        raise ValueError("definition_of_done is required")
    starting_point = payload.get("starting_point")
    if starting_point is not None and not isinstance(starting_point, str):
        raise ValueError("starting_point must be a string")
    builder_profile_id = payload.get("builder_profile_id")
    if builder_profile_id is not None and not isinstance(builder_profile_id, str):
        raise ValueError("builder_profile_id must be a string")
    judge_profile_id = payload.get("judge_profile_id")
    if judge_profile_id is not None and not isinstance(judge_profile_id, str):
        raise ValueError("judge_profile_id must be a string")
    pass_threshold_raw = payload.get("pass_threshold")
    pass_threshold = int(pass_threshold_raw) if isinstance(pass_threshold_raw, (int, float, str)) else None
    max_rounds_raw = payload.get("max_rounds")
    max_rounds = int(max_rounds_raw) if isinstance(max_rounds_raw, (int, float, str)) else None
    escalate_raw = payload.get("escalate_on_max_rounds")
    escalate_on_max_rounds = bool(escalate_raw) if escalate_raw is not None else True
    async_mode = bool(payload.get("async", True))

    config = BuilderJudgeConfig(
        definition_of_done=definition_of_done,
        starting_point=starting_point or None,
        builder_profile_id=builder_profile_id or DEFAULT_BUILDER_PROFILE,
        judge_profile_id=judge_profile_id or DEFAULT_JUDGE_PROFILE,
        pass_threshold=pass_threshold if pass_threshold is not None else DEFAULT_PASS_THRESHOLD,
        max_rounds=max_rounds if max_rounds is not None else DEFAULT_MAX_ROUNDS,
        escalate_on_max_rounds=escalate_on_max_rounds,
    )
    builder_judge_loop._validate_config(config)

    if async_mode:
        loop_id = builder_judge_loop._generate_loop_id()
        return start_builder_judge_async_loop(
            root,
            config,
            loop_id=loop_id,
            run_loop=run_builder_judge_loop,
        )

    run = run_builder_judge_loop(root, config)
    return project_builder_judge_run(run, root=root)


def build_builder_judge_list_payload(root: Path) -> dict[str, object]:
    return {"loops": bj_runtime._bj_list_visible_loops(root)}


def build_builder_judge_status_payload(root: Path, query: dict[str, list[str]]) -> dict[str, Any]:
    loop_id = (query.get("loop_id") or [None])[0]
    if not loop_id:
        raise ValueError("loop_id is required")

    run_data = bj_runtime._bj_get_running_loop(loop_id)
    if run_data is not None:
        if run_data.get("status") == "running":
            file_run = get_builder_judge_run(root, loop_id)
            if file_run and len(file_run.get("rounds", [])) > len(run_data.get("rounds", [])):
                return file_run
        return run_data

    run = get_builder_judge_run(root, loop_id)
    if run is None:
        raise BuilderJudgeRouteNotFound(f"Loop not found: {loop_id}")
    return run


def build_builder_judge_quality_gate_payload(repo_root: Path, payload: dict[str, object]) -> dict[str, Any]:
    root = _payload_project_root(repo_root, payload)
    session_id = payload.get("session_id")
    if not isinstance(session_id, str) or not session_id.strip():
        raise ValueError("session_id is required")
    stage = payload.get("stage")
    if not isinstance(stage, str) or stage not in ("spec", "plan"):
        raise ValueError("stage must be 'spec' or 'plan'")
    transcript_text = build_quality_gate_transcript_text(root, session_id)

    builder_profile_id = payload.get("builder_profile_id") or DEFAULT_BUILDER_PROFILE
    judge_profile_id = payload.get("judge_profile_id") or DEFAULT_JUDGE_PROFILE
    pass_threshold = int(payload.get("pass_threshold", DEFAULT_PASS_THRESHOLD))
    max_rounds = int(payload.get("max_rounds", 3))

    run = run_quality_gate(
        root,
        stage=stage,
        transcript_text=transcript_text,
        builder_profile_id=builder_profile_id,
        judge_profile_id=judge_profile_id,
        pass_threshold=pass_threshold,
        max_rounds=max_rounds,
    )
    return project_builder_judge_run(run, root=root)


def _payload_project_root(repo_root: Path, payload: dict[str, object]) -> Path:
    project_id = payload.get("project")
    if isinstance(project_id, str) and project_id.strip():
        return resolve_project_root(repo_root, project_id.strip()).root
    return repo_root
