"""Control plane aggregate — ticket/project/milestone/dependency state (M4-S1).

First-class ownership of ticket, project, milestone, and dependency state.
All types are frozen. No autonomous promotion — the control plane tracks
lifecycle but never creates branches, merges, pushes, or deploys.

Persistence::

    .devflow/control-plane/tickets/<ticket_id>.json
    .devflow/control-plane/projects/<project_id>.json
    .devflow/control-plane/milestones/<milestone_id>.json

All writes are atomic (temp + replace). The control plane never touches
pipeline-run directories or the workflow ledger.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._-]*$"


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class TicketStatus(str, Enum):
    """Lifecycle states for a ticket."""

    open = "open"
    in_progress = "in_progress"
    in_review = "in_review"
    blocked = "blocked"
    merged = "merged"
    closed = "closed"


# ---------------------------------------------------------------------------
# Frozen models
# ---------------------------------------------------------------------------

class Ticket(BaseModel):
    """One unit of work in the control plane."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    ticket_id: str = Field(pattern=_ID_PATTERN)
    title: str = Field(min_length=1)
    description: str = ""
    status: TicketStatus = TicketStatus.open
    project_id: str = ""
    milestone_id: str | None = None
    run_id: str | None = None  # linked pipeline run
    created_at: str = Field(min_length=1)
    updated_at: str = Field(min_length=1)


class Project(BaseModel):
    """A project that groups tickets."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    project_id: str = Field(pattern=_ID_PATTERN)
    name: str = Field(min_length=1)
    description: str = ""


class Milestone(BaseModel):
    """A milestone within a project."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    milestone_id: str = Field(pattern=_ID_PATTERN)
    project_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    ticket_ids: tuple[str, ...] = ()


class DependencyState(BaseModel):
    """Tracks cross-ticket dependencies."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    ticket_id: str = Field(pattern=_ID_PATTERN)
    depends_on: tuple[str, ...] = ()
    blocked_by: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# Storage helpers
# ---------------------------------------------------------------------------

def _control_plane_dir(root: Path | str) -> Path:
    return Path(root).resolve() / ".devflow" / "control-plane"


def _tickets_dir(root: Path | str) -> Path:
    return _control_plane_dir(root) / "tickets"


def _projects_dir(root: Path | str) -> Path:
    return _control_plane_dir(root) / "projects"


def _milestones_dir(root: Path | str) -> Path:
    return _control_plane_dir(root) / "milestones"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _atomic_write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    payload = json.dumps(data, indent=2, sort_keys=True) + "\n"
    tmp.write_text(payload, encoding="utf-8")
    os.replace(tmp, path)


def _read_json(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


# ---------------------------------------------------------------------------
# Ticket operations
# ---------------------------------------------------------------------------

def _new_ticket_id() -> str:
    """Generate a sortable ticket ID."""
    return f"ticket-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"


def create_ticket(
    root: Path | str,
    title: str,
    description: str = "",
    project_id: str = "",
    ticket_id: str | None = None,
) -> Ticket:
    """Create a new ticket and persist it.

    If ``ticket_id`` is not provided, one is generated.
    """
    tid = ticket_id or _new_ticket_id()
    now = _now_iso()
    ticket = Ticket(
        ticket_id=tid,
        title=title,
        description=description,
        project_id=project_id,
        created_at=now,
        updated_at=now,
    )
    path = _tickets_dir(root) / f"{tid}.json"
    if path.exists():
        raise ValueError(f"ticket {tid!r} already exists")
    _atomic_write_json(path, ticket.model_dump(mode="json"))
    return ticket


def get_ticket(root: Path | str, ticket_id: str) -> Ticket | None:
    """Load a ticket by ID. Returns None if not found."""
    path = _tickets_dir(root) / f"{ticket_id}.json"
    data = _read_json(path)
    if data is None:
        return None
    return Ticket.model_validate(data)


def update_ticket_status(
    root: Path | str,
    ticket_id: str,
    status: TicketStatus,
) -> Ticket:
    """Update a ticket's status. Returns the updated ticket.

    Raises ``ValueError`` if the ticket doesn't exist.
    """
    path = _tickets_dir(root) / f"{ticket_id}.json"
    data = _read_json(path)
    if data is None:
        raise ValueError(f"ticket {ticket_id!r} not found")
    ticket = Ticket.model_validate(data)
    updated = ticket.model_copy(update={
        "status": status,
        "updated_at": _now_iso(),
    })
    _atomic_write_json(path, updated.model_dump(mode="json"))
    return updated


def link_run_to_ticket(
    root: Path | str,
    ticket_id: str,
    run_id: str,
) -> Ticket:
    """Link a pipeline run to a ticket. Returns the updated ticket.

    Raises ``ValueError`` if the ticket doesn't exist.
    """
    path = _tickets_dir(root) / f"{ticket_id}.json"
    data = _read_json(path)
    if data is None:
        raise ValueError(f"ticket {ticket_id!r} not found")
    ticket = Ticket.model_validate(data)
    updated = ticket.model_copy(update={
        "run_id": run_id,
        "updated_at": _now_iso(),
    })
    _atomic_write_json(path, updated.model_dump(mode="json"))
    return updated


def list_tickets(
    root: Path | str,
    project_id: str | None = None,
) -> tuple[Ticket, ...]:
    """List all tickets, optionally filtered by project.

    Returns tickets sorted by ticket_id for stable ordering.
    """
    tickets_dir = _tickets_dir(root)
    if not tickets_dir.is_dir():
        return ()

    tickets: list[Ticket] = []
    for child in sorted(tickets_dir.iterdir()):
        if not child.is_file() or child.suffix != ".json":
            continue
        data = _read_json(child)
        if data is None:
            continue
        try:
            ticket = Ticket.model_validate(data)
        except Exception:
            continue
        if project_id is not None and ticket.project_id != project_id:
            continue
        tickets.append(ticket)

    return tuple(tickets)


# ---------------------------------------------------------------------------
# Project operations
# ---------------------------------------------------------------------------

def create_project(
    root: Path | str,
    name: str,
    description: str = "",
    project_id: str | None = None,
) -> Project:
    """Create a new project and persist it."""
    import secrets

    pid = project_id or f"proj-{secrets.token_hex(4)}"
    project = Project(
        project_id=pid,
        name=name,
        description=description,
    )
    path = _projects_dir(root) / f"{pid}.json"
    if path.exists():
        raise ValueError(f"project {pid!r} already exists")
    _atomic_write_json(path, project.model_dump(mode="json"))
    return project


def get_project(root: Path | str, project_id: str) -> Project | None:
    """Load a project by ID."""
    path = _projects_dir(root) / f"{project_id}.json"
    data = _read_json(path)
    if data is None:
        return None
    return Project.model_validate(data)


# ---------------------------------------------------------------------------
# Milestone operations
# ---------------------------------------------------------------------------

def create_milestone(
    root: Path | str,
    project_id: str,
    name: str,
    milestone_id: str | None = None,
    ticket_ids: tuple[str, ...] = (),
) -> Milestone:
    """Create a milestone within a project."""
    import secrets

    mid = milestone_id or f"ms-{secrets.token_hex(4)}"
    milestone = Milestone(
        milestone_id=mid,
        project_id=project_id,
        name=name,
        ticket_ids=ticket_ids,
    )
    path = _milestones_dir(root) / f"{mid}.json"
    if path.exists():
        raise ValueError(f"milestone {mid!r} already exists")
    _atomic_write_json(path, milestone.model_dump(mode="json"))
    return milestone


# ---------------------------------------------------------------------------
# Dependency operations
# ---------------------------------------------------------------------------

def set_dependency(
    root: Path | str,
    ticket_id: str,
    depends_on: tuple[str, ...],
) -> DependencyState:
    """Set a ticket's dependencies. Returns the dependency state.

    ``blocked_by`` is computed from unresolved dependencies.
    """
    deps = DependencyState(
        ticket_id=ticket_id,
        depends_on=depends_on,
        blocked_by=tuple(
            dep for dep in depends_on
            if _is_dependency_open(root, dep)
        ),
    )
    return deps


def _is_dependency_open(root: Path | str, ticket_id: str) -> bool:
    """True if a dependency ticket is not closed/merged."""
    ticket = get_ticket(root, ticket_id)
    if ticket is None:
        return True  # unknown dependency is treated as open/blocking
    return ticket.status not in (TicketStatus.closed, TicketStatus.merged)


__all__ = [
    "DependencyState",
    "Milestone",
    "Project",
    "Ticket",
    "TicketStatus",
    "create_milestone",
    "create_project",
    "create_ticket",
    "get_project",
    "get_ticket",
    "link_run_to_ticket",
    "list_tickets",
    "set_dependency",
    "update_ticket_status",
]
