"""Tests for the control plane aggregate (M4-S1)."""

from __future__ import annotations

from pathlib import Path

import pytest

from devflow.control_plane.aggregate import (
    DependencyState,
    Ticket,
    TicketStatus,
    create_milestone,
    create_project,
    create_ticket,
    get_project,
    get_ticket,
    link_run_to_ticket,
    list_tickets,
    set_dependency,
    update_ticket_status,
)


# ---------------------------------------------------------------------------
# Ticket lifecycle tests
# ---------------------------------------------------------------------------

def test_ticket_creation(tmp_path: Path) -> None:
    """create returns frozen Ticket."""
    ticket = create_ticket(tmp_path, title="Add feature X")

    assert ticket.title == "Add feature X"
    assert ticket.status == TicketStatus.open
    assert ticket.ticket_id.startswith("ticket-")
    assert ticket.created_at == ticket.updated_at


def test_ticket_lifecycle(tmp_path: Path) -> None:
    """open → in_progress → in_review → merged."""
    ticket = create_ticket(tmp_path, title="Fix bug Y")

    t1 = update_ticket_status(tmp_path, ticket.ticket_id, TicketStatus.in_progress)
    assert t1.status == TicketStatus.in_progress

    t2 = update_ticket_status(tmp_path, ticket.ticket_id, TicketStatus.in_review)
    assert t2.status == TicketStatus.in_review

    t3 = update_ticket_status(tmp_path, ticket.ticket_id, TicketStatus.merged)
    assert t3.status == TicketStatus.merged


def test_ticket_status_update_returns_new(tmp_path: Path) -> None:
    """update returns a new Ticket with new status."""
    original = create_ticket(tmp_path, title="Test")
    updated = update_ticket_status(tmp_path, original.ticket_id, TicketStatus.blocked)

    assert updated.status == TicketStatus.blocked
    assert original.status == TicketStatus.open  # original unchanged


def test_ticket_link_run(tmp_path: Path) -> None:
    """link_run_to_ticket sets run_id."""
    ticket = create_ticket(tmp_path, title="Test")
    updated = link_run_to_ticket(tmp_path, ticket.ticket_id, "run-12345")

    assert updated.run_id == "run-12345"


def test_ticket_frozen() -> None:
    """Ticket is immutable."""
    t = Ticket(
        ticket_id="t1", title="Test",
        created_at="2026-01-01T00:00:00Z", updated_at="2026-01-01T00:00:00Z",
    )
    with pytest.raises(Exception):
        t.title = "modified"  # type: ignore[misc]


def test_get_ticket_not_found(tmp_path: Path) -> None:
    """Returns None when ticket doesn't exist."""
    assert get_ticket(tmp_path, "nonexistent") is None


def test_get_ticket_persisted(tmp_path: Path) -> None:
    """get_ticket loads a persisted ticket."""
    ticket = create_ticket(tmp_path, title="Persisted", ticket_id="t-persist")
    loaded = get_ticket(tmp_path, "t-persist")

    assert loaded is not None
    assert loaded.ticket_id == "t-persist"
    assert loaded.title == "Persisted"


def test_ticket_duplicate_id_rejected(tmp_path: Path) -> None:
    """Duplicate ticket_id → ValueError."""
    create_ticket(tmp_path, title="First", ticket_id="t-dup")
    with pytest.raises(ValueError, match="already exists"):
        create_ticket(tmp_path, title="Second", ticket_id="t-dup")


def test_update_nonexistent_ticket_raises(tmp_path: Path) -> None:
    """Updating a nonexistent ticket → ValueError."""
    with pytest.raises(ValueError, match="not found"):
        update_ticket_status(tmp_path, "ghost", TicketStatus.closed)


# ---------------------------------------------------------------------------
# Project tests
# ---------------------------------------------------------------------------

def test_project_creation(tmp_path: Path) -> None:
    """create project persists."""
    project = create_project(tmp_path, name="DevFlow", description="The main project")

    assert project.name == "DevFlow"
    assert project.project_id.startswith("proj-")

    loaded = get_project(tmp_path, project.project_id)
    assert loaded is not None
    assert loaded.name == "DevFlow"


def test_project_duplicate_rejected(tmp_path: Path) -> None:
    create_project(tmp_path, name="P1", project_id="p-dup")
    with pytest.raises(ValueError, match="already exists"):
        create_project(tmp_path, name="P2", project_id="p-dup")


# ---------------------------------------------------------------------------
# Milestone tests
# ---------------------------------------------------------------------------

def test_milestone_creation(tmp_path: Path) -> None:
    """Milestone with ticket_ids."""
    create_project(tmp_path, name="P1", project_id="p1")
    t1 = create_ticket(tmp_path, title="T1", project_id="p1", ticket_id="t-ms-1")
    t2 = create_ticket(tmp_path, title="T2", project_id="p1", ticket_id="t-ms-2")

    ms = create_milestone(
        tmp_path,
        project_id="p1",
        name="v1.0",
        ticket_ids=(t1.ticket_id, t2.ticket_id),
    )

    assert ms.name == "v1.0"
    assert len(ms.ticket_ids) == 2


# ---------------------------------------------------------------------------
# Dependency tests
# ---------------------------------------------------------------------------

def test_dependency_state(tmp_path: Path) -> None:
    """depends_on and blocked_by."""
    t1 = create_ticket(tmp_path, title="T1", ticket_id="t-dep-1")
    create_ticket(tmp_path, title="T2", ticket_id="t-dep-2")

    deps = set_dependency(tmp_path, "t-dep-1", depends_on=("t-dep-2",))

    assert deps.depends_on == ("t-dep-2",)
    # t-dep-2 is open → t-dep-1 is blocked by it
    assert deps.blocked_by == ("t-dep-2",)


def test_dependency_resolved_when_closed(tmp_path: Path) -> None:
    """Dependency not blocking when closed."""
    create_ticket(tmp_path, title="T1", ticket_id="t-a")
    create_ticket(tmp_path, title="T2", ticket_id="t-b")
    update_ticket_status(tmp_path, "t-b", TicketStatus.closed)

    deps = set_dependency(tmp_path, "t-a", depends_on=("t-b",))

    assert deps.blocked_by == ()  # t-b is closed → not blocking


def test_dependency_unknown_ticket_blocks(tmp_path: Path) -> None:
    """Unknown dependency is treated as open/blocking."""
    create_ticket(tmp_path, title="T1", ticket_id="t-x")

    deps = set_dependency(tmp_path, "t-x", depends_on=("nonexistent",))

    assert deps.blocked_by == ("nonexistent",)


# ---------------------------------------------------------------------------
# list_tickets tests
# ---------------------------------------------------------------------------

def test_list_tickets_by_project(tmp_path: Path) -> None:
    """Filter by project_id."""
    create_ticket(tmp_path, title="T1", project_id="p-a", ticket_id="t1")
    create_ticket(tmp_path, title="T2", project_id="p-a", ticket_id="t2")
    create_ticket(tmp_path, title="T3", project_id="p-b", ticket_id="t3")

    result = list_tickets(tmp_path, project_id="p-a")

    assert len(result) == 2
    assert all(t.project_id == "p-a" for t in result)


def test_list_tickets_all(tmp_path: Path) -> None:
    """All tickets when no filter."""
    create_ticket(tmp_path, title="T1", ticket_id="t1")
    create_ticket(tmp_path, title="T2", ticket_id="t2")

    result = list_tickets(tmp_path)

    assert len(result) == 2


def test_list_tickets_empty(tmp_path: Path) -> None:
    """Empty tuple when no tickets exist."""
    assert list_tickets(tmp_path) == ()


# ---------------------------------------------------------------------------
# Separation and safety tests
# ---------------------------------------------------------------------------

def test_no_promotion_side_effects(tmp_path: Path) -> None:
    """No branch creation or merge from control plane."""
    ticket = create_ticket(tmp_path, title="Test")
    update_ticket_status(tmp_path, ticket.ticket_id, TicketStatus.merged)

    # Verify no result branches were created
    result_dir = tmp_path / ".devflow" / "pipeline-runs"
    assert not result_dir.exists() or not any(result_dir.iterdir())


def test_control_plane_separate_from_runs(tmp_path: Path) -> None:
    """Tickets stored separately from pipeline-runs."""
    create_ticket(tmp_path, title="Test", ticket_id="t-sep")

    tickets_dir = tmp_path / ".devflow" / "control-plane" / "tickets"
    runs_dir = tmp_path / ".devflow" / "pipeline-runs"

    assert (tickets_dir / "t-sep.json").is_file()
    # pipeline-runs should not exist or be empty
    assert not runs_dir.exists() or not any(runs_dir.iterdir())


def test_ticket_round_trips_json(tmp_path: Path) -> None:
    """Ticket survives JSON serialization."""
    import json

    ticket = create_ticket(tmp_path, title="Round Trip", ticket_id="t-rt")
    path = tmp_path / ".devflow" / "control-plane" / "tickets" / "t-rt.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    restored = Ticket.model_validate(data)

    assert restored == ticket


def test_dependency_state_frozen() -> None:
    """DependencyState is immutable."""
    deps = DependencyState(ticket_id="t1")
    with pytest.raises(Exception):
        deps.depends_on = ("x",)  # type: ignore[misc]
