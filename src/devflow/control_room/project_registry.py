from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass
from datetime import timezone
from pathlib import Path
from typing import Any

import yaml

from devflow.control_room.persistence import atomic_write_text, utc_now
from devflow.control_room.project_models import (
    ProjectMetadata,
    ProjectPublicationPolicy,
    ProjectRecord,
    ProjectRegistry,
    ProjectSourceControl,
    ProjectSourceControlMode,
    ProjectVersionControl,
)


class ProjectRegistryError(ValueError):
    pass


@dataclass(frozen=True)
class ProjectRootResolution:
    root: Path
    project_id: str | None
    source: str = "cwd"


def devflow_home(home: Path | None = None) -> Path:
    if home is not None:
        return home.expanduser().resolve()
    env_home = os.getenv("DEVFLOW_HOME")
    if env_home:
        return Path(env_home).expanduser().resolve()
    return Path.home() / ".devflow"


def default_projects_root(home: Path | None = None) -> Path:
    if home is not None or os.getenv("DEVFLOW_HOME"):
        return devflow_home(home).parent / "DevFlow Projects"
    return Path.home() / "DevFlow Projects"


def registry_path(home: Path | None = None) -> Path:
    return devflow_home(home) / "registry" / "projects.json"


def registry_events_path(home: Path | None = None) -> Path:
    return devflow_home(home) / "events.jsonl"


def normalize_project_id(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    slug = re.sub(r"-+", "-", slug)
    if not slug:
        raise ProjectRegistryError("Project id must contain at least one letter or number.")
    return slug


def normalize_source_control_mode(value: str) -> ProjectSourceControlMode:
    normalized = value.strip().lower().replace("-", "_")
    allowed = {"none", "local_git", "remote_git", "github_managed"}
    if normalized not in allowed:
        raise ProjectRegistryError(
            "source control must be one of: none, local-git, remote-git, github-managed"
        )
    return normalized  # type: ignore[return-value]


def infer_remote_provider(remote_url: str | None) -> str:
    if not remote_url:
        return "none"
    lowered = remote_url.lower()
    if "github.com" in lowered:
        return "github"
    if "gitlab.com" in lowered:
        return "gitlab"
    if "bitbucket.org" in lowered:
        return "bitbucket"
    return "git"


def load_registry(home: Path | None = None) -> ProjectRegistry:
    path = registry_path(home)
    if not path.exists():
        return ProjectRegistry(projects_root=default_projects_root(home).as_posix(), projects=[])
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ProjectRegistryError(f"Project registry is invalid JSON: {exc.msg}") from exc
    try:
        return ProjectRegistry.model_validate(payload)
    except Exception as exc:
        raise ProjectRegistryError(f"Project registry is malformed: {exc}") from exc


def save_registry(registry: ProjectRegistry, home: Path | None = None) -> None:
    path = registry_path(home)
    payload = registry.model_dump(mode="json")
    atomic_write_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")


def set_projects_root(projects_root: Path, *, home: Path | None = None) -> ProjectRegistry:
    registry = load_registry(home)
    registry.projects_root = projects_root.expanduser().resolve().as_posix()
    save_registry(registry, home)
    return registry


def append_registry_event(event: str, payload: dict[str, Any], home: Path | None = None) -> None:
    path = registry_events_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "timestamp": utc_now().astimezone(timezone.utc).isoformat(),
        "event": event,
        **payload,
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def register_project(record: ProjectRecord, *, home: Path | None = None, replace: bool = False) -> ProjectRegistry:
    registry = load_registry(home)
    existing_index: int | None = None
    for index, existing in enumerate(registry.projects):
        if existing.project_id == record.project_id:
            existing_index = index
            break
        if Path(existing.path).resolve() == Path(record.path).resolve():
            raise ProjectRegistryError(
                f"Project path is already registered as {existing.project_id}: {existing.path}"
            )
    if existing_index is not None:
        if not replace:
            raise ProjectRegistryError(f"Project already registered: {record.project_id}")
        registry.projects[existing_index] = record
        event = "project_updated"
    else:
        registry.projects.append(record)
        event = "project_registered"
    registry.projects = sorted(registry.projects, key=lambda item: item.project_id)
    save_registry(registry, home)
    append_registry_event(event, {"project_id": record.project_id, "path": record.path}, home)
    return registry


def list_project_records(*, include_archived: bool = False, home: Path | None = None) -> list[ProjectRecord]:
    records = load_registry(home).projects
    if include_archived:
        return records
    return [record for record in records if record.status != "archived"]


def get_project_record(project_id: str, *, home: Path | None = None) -> ProjectRecord:
    lookup = normalize_project_id(project_id)
    for record in load_registry(home).projects:
        if record.project_id == lookup:
            return record
    raise ProjectRegistryError(f"Project not found: {lookup}")


def resolve_project_root(current_root: Path, project_id: str | None, *, home: Path | None = None) -> ProjectRootResolution:
    if project_id is None:
        return resolve_current_project_root(current_root)
    record = get_project_record(project_id, home=home)
    root = Path(record.path).expanduser().resolve()
    if record.status == "archived":
        raise ProjectRegistryError(f"Project is archived: {record.project_id}")
    if not root.is_dir():
        raise ProjectRegistryError(f"Project path is missing: {root}")
    return ProjectRootResolution(root=root, project_id=record.project_id, source="registry")


def resolve_current_project_root(start: Path) -> ProjectRootResolution:
    """Resolve implicit project commands to the nearest ancestor with .devflow state."""
    current = start.expanduser().resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".devflow").is_dir():
            project_id = None
            try:
                metadata = load_project_metadata(candidate)
                project_id = metadata.project_id
            except ProjectRegistryError:
                project_id = None
            return ProjectRootResolution(root=candidate, project_id=project_id, source="ancestor")
    return ProjectRootResolution(root=current, project_id=None, source="cwd")


def project_task_ref(task_id: str, project_id: str | None) -> str:
    return f"{project_id}:{task_id}" if project_id else task_id


def archive_project(project_id: str, *, home: Path | None = None) -> ProjectRecord:
    record = get_project_record(project_id, home=home)
    updated = record.model_copy(update={"status": "archived", "last_seen_at": utc_now()})
    register_project(updated, home=home, replace=True)
    append_registry_event("project_archived", {"project_id": updated.project_id}, home)
    return updated


def remove_project(project_id: str, *, home: Path | None = None) -> ProjectRecord:
    lookup = normalize_project_id(project_id)
    registry = load_registry(home)
    remaining: list[ProjectRecord] = []
    removed: ProjectRecord | None = None
    for record in registry.projects:
        if record.project_id == lookup:
            removed = record
        else:
            remaining.append(record)
    if removed is None:
        raise ProjectRegistryError(f"Project not found: {lookup}")
    registry.projects = remaining
    save_registry(registry, home)
    append_registry_event("project_removed", {"project_id": removed.project_id}, home)
    return removed


def project_metadata_path(root: Path) -> Path:
    return root / ".devflow" / "project" / "project.yaml"


def load_project_metadata(root: Path) -> ProjectMetadata:
    path = project_metadata_path(root)
    if not path.exists():
        raise ProjectRegistryError(f"Project metadata is missing: {path}")
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ProjectRegistryError(f"Project metadata is malformed YAML: {exc}") from exc
    if not isinstance(payload, dict):
        raise ProjectRegistryError("Project metadata must be a YAML mapping.")
    if "project_id" not in payload and "id" in payload:
        payload["project_id"] = payload["id"]
    if "id" not in payload and "project_id" in payload:
        payload["id"] = payload["project_id"]
    try:
        return ProjectMetadata.model_validate(payload)
    except Exception as exc:
        raise ProjectRegistryError(f"Project metadata is malformed: {exc}") from exc


def write_project_metadata(root: Path, metadata: ProjectMetadata) -> None:
    payload = metadata.model_dump(mode="json", exclude_none=False)
    atomic_write_text(project_metadata_path(root), yaml.safe_dump(payload, sort_keys=False))


def build_project_record(metadata: ProjectMetadata) -> ProjectRecord:
    return ProjectRecord(
        project_id=metadata.project_id,
        name=metadata.name,
        path=metadata.root_path,
        status=metadata.status,
        source_control_mode=metadata.source_control.mode,
        remote_provider=metadata.source_control.remote_provider,
        remote_url=metadata.source_control.remote_url,
        last_seen_at=utc_now(),
    )


def project_publication_policy(root: Path) -> ProjectPublicationPolicy | None:
    try:
        metadata = load_project_metadata(root)
    except ProjectRegistryError:
        return None
    return metadata.remote_publication


def render_project_list(*, include_archived: bool = False, home: Path | None = None) -> str:
    registry = load_registry(home)
    records = list_project_records(include_archived=include_archived, home=home)
    lines = [
        "DevFlow Projects",
        f"  Registry: {registry_path(home)}",
        f"  Projects root: {registry.projects_root}",
        "",
        f"{'Project':<24} {'Status':<10} {'SCM':<12} {'Path status':<12} Path",
        "-" * 96,
    ]
    if not records:
        lines.append("No projects registered.")
    for record in records:
        path_status = "present" if Path(record.path).exists() else "missing"
        lines.append(
            f"{record.project_id:<24} {record.status:<10} {record.source_control_mode:<12} "
            f"{path_status:<12} {record.path}"
        )
    return "\n".join(lines) + "\n"


def render_project_show(project_id: str, *, home: Path | None = None) -> str:
    record = get_project_record(project_id, home=home)
    path = Path(record.path)
    lines = [
        f"Project: {record.project_id}",
        f"  Name: {record.name}",
        f"  Status: {record.status}",
        f"  Path: {record.path}",
        f"  Path status: {'present' if path.exists() else 'missing'}",
        f"  Source control: {record.source_control_mode}",
        f"  Remote provider: {record.remote_provider}",
        f"  Remote URL: {record.remote_url or 'none'}",
        f"  Last seen: {record.last_seen_at.isoformat()}",
    ]
    if path.exists():
        try:
            metadata = load_project_metadata(path)
            lines.extend(
                [
                    f"  Push allowed: {'yes' if metadata.remote_publication.push_allowed else 'no'}",
                    f"  Publish allowed: {'yes' if metadata.remote_publication.publish_allowed else 'no'}",
                    f"  Track DevFlow context: {'yes' if metadata.version_control.track_devflow_context else 'no'}",
                ]
            )
        except ProjectRegistryError as exc:
            lines.append(f"  Metadata: invalid ({exc})")
    return "\n".join(lines) + "\n"


def render_project_status(project_id: str, *, home: Path | None = None) -> str:
    record = get_project_record(project_id, home=home)
    path = Path(record.path)
    lines = [
        f"Project Status: {record.project_id}",
        f"  Path: {record.path}",
        f"  Path status: {'present' if path.exists() else 'missing'}",
    ]
    if not path.exists():
        lines.append("  Task health: unavailable")
        return "\n".join(lines) + "\n"
    from devflow.control_room.dashboard import collect_dashboard_state

    state = collect_dashboard_state(path)
    lines.extend(
        [
            f"  Branch: {state.project.branch or 'unknown'}",
            f"  Working tree: {state.project.working_tree or 'unknown'}",
            f"  Tasks: {state.health.total_tasks}",
            f"  Active: {state.health.active_tasks}",
            f"  Needs verification: {state.health.needs_verification}",
            f"  Ready to promote: {state.health.ready_to_promote}",
            f"  Next: {state.next_action.command or 'None'}",
        ]
    )
    return "\n".join(lines) + "\n"


def doctor_project(project_id: str, *, home: Path | None = None) -> list[tuple[str, bool, str]]:
    record = get_project_record(project_id, home=home)
    root = Path(record.path)
    checks: list[tuple[str, bool, str]] = [
        ("registry record", True, record.project_id),
        ("project path", root.exists(), root.as_posix()),
    ]
    if not root.exists():
        return checks
    try:
        metadata = load_project_metadata(root)
        checks.append(("project metadata", True, project_metadata_path(root).as_posix()))
    except ProjectRegistryError as exc:
        checks.append(("project metadata", False, str(exc)))
        return checks
    checks.append(("metadata id matches registry", metadata.project_id == record.project_id, metadata.project_id))
    git_exists = (root / ".git").exists()
    if metadata.source_control.mode == "none":
        checks.append(("local git disabled", not git_exists, ".git should be absent"))
    else:
        checks.append(("local git repo", git_exists, ".git"))
        remote = _git_remote_url(root)
        if metadata.source_control.mode == "local_git":
            checks.append(("no remote", remote is None, remote or "none"))
        if metadata.source_control.mode == "remote_git":
            checks.append(("remote url configured", remote is not None, remote or "missing"))
    return checks


def _git_remote_url(root: Path) -> str | None:
    proc = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return None
    return proc.stdout.strip() or None


def source_control_from_git(root: Path) -> ProjectSourceControl:
    if not (root / ".git").exists():
        return ProjectSourceControl(mode="none", local_repo=False, remote_provider="none", remote_url=None)
    remote_url = _git_remote_url(root)
    if remote_url:
        return ProjectSourceControl(
            mode="remote_git",
            local_repo=True,
            remote_provider=infer_remote_provider(remote_url),
            remote_url=remote_url,
        )
    return ProjectSourceControl(mode="local_git", local_repo=True, remote_provider="none", remote_url=None)


def update_project_remote_policy(
    project_id: str,
    *,
    remote_url: str,
    push_allowed: bool = False,
    home: Path | None = None,
) -> ProjectMetadata:
    record = get_project_record(project_id, home=home)
    root = Path(record.path)
    if not (root / ".git").exists():
        raise ProjectRegistryError(f"Project is not a local Git repo: {record.project_id}")
    current_remote = _git_remote_url(root)
    if current_remote:
        subprocess.run(["git", "remote", "set-url", "origin", remote_url], cwd=root, capture_output=True, text=True, check=True)
    else:
        subprocess.run(["git", "remote", "add", "origin", remote_url], cwd=root, capture_output=True, text=True, check=True)
    metadata = load_project_metadata(root)
    metadata.source_control = ProjectSourceControl(
        mode="remote_git",
        local_repo=True,
        remote_provider=infer_remote_provider(remote_url),
        remote_url=remote_url,
    )
    metadata.remote_publication.push_allowed = push_allowed
    metadata.remote_publication.publish_allowed = push_allowed
    write_project_metadata(root, metadata)
    updated = build_project_record(metadata)
    register_project(updated, home=home, replace=True)
    return metadata


def track_devflow_context_policy(private_context: bool) -> ProjectVersionControl:
    return ProjectVersionControl(track_devflow_context=not private_context)
