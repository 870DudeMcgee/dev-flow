from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


TaskStatus = Literal[
    "created",
    "running",
    "complete",
    "verified",
    "verification_failed",
    "failed",
    "blocked",
    "worker_failed",
    "timeout",
    "promoted",
    "closed",
]

WorkerPermissionMode = Literal[
    "read_only",
    "workspace_write",
    "verify_only",
    "promotion_candidate",
]

ALLOWED_PERMISSION_MODES: list[WorkerPermissionMode] = [
    "read_only",
    "workspace_write",
    "verify_only",
    "promotion_candidate",
]


TASK_SCHEMA_VERSION = 1


class TaskRecord(BaseModel):
    schema_version: int = TASK_SCHEMA_VERSION
    id: str
    title: str
    status: TaskStatus = "created"
    created_at: datetime
    updated_at: datetime
    workspace: str
    worker: str = "shell"
    last_event: str | None = None
    last_exit_code: int | None = None
    verification_status: str = "not_run"
    worker_adapter: str | None = None
    workspace_path: str | None = None
    workspace_kind: str | None = None
    branch_name: str | None = None
    workspace_commit: str | None = None
    workspace_dirty: bool | None = None
    latest_log_line: str | None = None
    log_path: str | None = None
    result_path: str | None = None
    worker_command: str | None = None
    verification_command: str | None = None
    verification_exit_code: int | None = None
    verification_log_path: str | None = None
    exit_code: int | None = None
    timeout_seconds: int | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    close_outcome: str | None = None
    close_reason: str | None = None
    closed_at: datetime | None = None

    @property
    def merge_ready(self) -> bool:
        return self.status == "verified"

    def model_post_init(self, __context: object) -> None:
        self.workspace_path = self.workspace_path or self.workspace
        self.worker_adapter = self.worker_adapter or self.worker
        self.exit_code = self.exit_code if self.exit_code is not None else self.last_exit_code


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
    env: dict[str, str] = Field(default_factory=dict)
    timeout_seconds: int = Field(default=60, ge=1)

    model_config = {"arbitrary_types_allowed": True}


class WorkerResult(BaseModel):
    status: Literal["complete", "worker_failed", "timeout", "blocked"]
    summary: str
    exit_code: int | None = None
    latest_log_line: str | None = None
    result_file: Path
    log_file: Path

    model_config = {"arbitrary_types_allowed": True}
