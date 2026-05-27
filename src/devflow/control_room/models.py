from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


TaskStatus = Literal[
    "draft",
    "running",
    "complete",
    "worker_failed",
    "timeout",
]


class TaskRecord(BaseModel):
    id: str
    title: str
    status: TaskStatus = "draft"
    worker_adapter: str | None = None
    workspace_path: str | None = None
    workspace_kind: str | None = None
    branch_name: str | None = None
    latest_log_line: str | None = None
    log_path: str | None = None
    result_path: str | None = None
    verification_status: str | None = None
    verification_command: str | None = None
    verification_exit_code: int | None = None
    verification_log_path: str | None = None
    merge_ready: bool = False
    exit_code: int | None = None
    timeout_seconds: int | None = None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None


class WorkerInput(BaseModel):
    task_id: str
    repo_root: Path
    workspace_path: Path
    task_file: Path
    context_file: Path
    status_file: Path
    questions_file: Path
    result_file: Path
    log_file: Path
    command: list[str]
    timeout_seconds: int = Field(default=60, ge=1)

    model_config = {"arbitrary_types_allowed": True}


class WorkerResult(BaseModel):
    status: Literal["complete", "worker_failed", "timeout"]
    summary: str
    exit_code: int | None = None
    latest_log_line: str | None = None
    result_file: Path
    log_file: Path

    model_config = {"arbitrary_types_allowed": True}
