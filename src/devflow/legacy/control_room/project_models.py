from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


PROJECT_SCHEMA_VERSION = 1

ProjectSourceControlMode = Literal["none", "local_git", "remote_git", "github_managed"]
ProjectStatus = Literal["active", "archived"]


class ProjectSourceControl(BaseModel):
    mode: ProjectSourceControlMode = "local_git"
    local_repo: bool = True
    remote_provider: str = "none"
    remote_url: str | None = None


class ProjectPublicationPolicy(BaseModel):
    create_remote_allowed: bool = False
    push_allowed: bool = False
    pull_request_allowed: bool = False
    publish_allowed: bool = False
    requires_human_confirmation: bool = True


class ProjectTaskDefaults(BaseModel):
    preferred_lane: str = "git_worktree"
    fallback_lane: str = "copy_workspace"
    verification_required_before_promotion: bool = True


class ProjectPrivacy(BaseModel):
    default_visibility: str = "local_only"
    allow_github_upload: bool = False
    allow_remote_provider_context: bool = False


class ProjectVersionControl(BaseModel):
    track_devflow_context: bool = True


class ProjectMetadata(BaseModel):
    schema_version: int = PROJECT_SCHEMA_VERSION
    id: str
    project_id: str
    name: str
    status: ProjectStatus = "active"
    purpose: str = "Managed by DevFlow."
    root_path: str
    created_by: str = "devflow"
    source_control: ProjectSourceControl = Field(default_factory=ProjectSourceControl)
    remote_publication: ProjectPublicationPolicy = Field(default_factory=ProjectPublicationPolicy)
    task_defaults: ProjectTaskDefaults = Field(default_factory=ProjectTaskDefaults)
    privacy: ProjectPrivacy = Field(default_factory=ProjectPrivacy)
    version_control: ProjectVersionControl = Field(default_factory=ProjectVersionControl)


class ProjectRecord(BaseModel):
    project_id: str
    name: str
    path: str
    status: ProjectStatus = "active"
    source_control_mode: ProjectSourceControlMode = "local_git"
    remote_provider: str = "none"
    remote_url: str | None = None
    last_seen_at: datetime


class ProjectRegistry(BaseModel):
    schema_version: int = PROJECT_SCHEMA_VERSION
    projects_root: str
    projects: list[ProjectRecord] = Field(default_factory=list)
