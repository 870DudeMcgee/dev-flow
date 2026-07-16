"""First-class Blocker and Handoff receipts (M4-S5, blueprint §5.2).

Makes ``Blocker`` and ``Handoff`` persisted first-class objects alongside the
existing ``DecisionReceipt`` (which is already first-class via the workflow
ledger). Each carries cause/owner/resolution and supports count queries.

Persistence is in separate files (``blocker-events.jsonl``,
``handoff-events.jsonl``) — never touches ``decision-events.jsonl`` or
``workflow-events.jsonl``. ``DecisionReceipt`` is never mutated.

Blueprint §5.2:

- **Blocker**: a condition preventing progress (dependency, missing input,
  repeated failure, resource conflict, policy denial).
- **Decision**: a choice requiring explicit authority (already first-class
  via ``DecisionReceipt``).
- **Handoff**: a structured transfer from one worker/stage to another.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from devflow.loop.pipeline_run import pipeline_runs_dir

_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:-]*$"

BLOCKER_EVENTS_FILE = "blocker-events.jsonl"
HANDOFF_EVENTS_FILE = "handoff-events.jsonl"


# ---------------------------------------------------------------------------
# Blocker
# ---------------------------------------------------------------------------

class BlockerReceipt(BaseModel):
    """One persisted blocker with cause, owner, and resolution state."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    blocker_id: str = Field(pattern=_ID_PATTERN)
    run_id: str = Field(pattern=_ID_PATTERN)
    node_id: str = Field(pattern=_ID_PATTERN)
    cause: str = Field(min_length=1)
    owner: str = "system"
    resolution: str = ""
    resolved: bool = False
    created_at: str = Field(min_length=1)
    resolved_at: str | None = None
    schema_version: Literal[1] = 1


# ---------------------------------------------------------------------------
# Handoff
# ---------------------------------------------------------------------------

class HandoffReceipt(BaseModel):
    """One persisted handoff between workflow stages or workers."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    handoff_id: str = Field(pattern=_ID_PATTERN)
    run_id: str = Field(pattern=_ID_PATTERN)
    from_node: str = Field(pattern=_ID_PATTERN)
    to_node: str = Field(pattern=_ID_PATTERN)
    artifact_refs: tuple[str, ...] = ()
    acceptance_status: Literal["pending", "accepted", "rejected"] = "pending"
    created_at: str = Field(min_length=1)
    schema_version: Literal[1] = 1


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_dir(root: Path | str, run_id: str) -> Path:
    return pipeline_runs_dir(root) / run_id


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _append_event(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, sort_keys=True) + "\n"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def _load_events(path: Path, model_cls: type) -> tuple:
    if not path.is_file():
        return ()
    items = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            items.append(model_cls.model_validate_json(line))
        except Exception:
            continue
    return tuple(items)


# ---------------------------------------------------------------------------
# Blocker operations
# ---------------------------------------------------------------------------

def record_blocker(
    root: Path | str,
    run_id: str,
    receipt: BlockerReceipt,
) -> BlockerReceipt:
    """Persist a blocker to ``blocker-events.jsonl``."""
    run_dir = _run_dir(root, run_id)
    if not run_dir.is_dir():
        raise FileNotFoundError(f"Pipeline run not found: {run_id}")

    events_path = run_dir / BLOCKER_EVENTS_FILE

    # Check for duplicate / idempotent
    if events_path.exists():
        for line in events_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                existing = BlockerReceipt.model_validate_json(line)
            except Exception:
                continue
            if existing.blocker_id == receipt.blocker_id:
                if existing == receipt:
                    return existing  # idempotent
                raise ValueError(
                    f"duplicate blocker id: {receipt.blocker_id}"
                )

    _append_event(events_path, receipt.model_dump(mode="json"))
    return receipt


def resolve_blocker(
    root: Path | str,
    run_id: str,
    blocker_id: str,
    resolution: str,
) -> BlockerReceipt | None:
    """Mark a blocker as resolved.

    Reads all blockers, replaces the matching one with a resolved version,
    and rewrites the events file. Returns the resolved receipt, or ``None``
    if the blocker was not found.
    """
    run_dir = _run_dir(root, run_id)
    events_path = run_dir / BLOCKER_EVENTS_FILE
    if not events_path.is_file():
        return None

    blockers = list(_load_events(events_path, BlockerReceipt))
    found = False
    resolved_receipt: BlockerReceipt | None = None

    for i, blocker in enumerate(blockers):
        if blocker.blocker_id == blocker_id and not blocker.resolved:
            resolved_receipt = blocker.model_copy(update={
                "resolved": True,
                "resolution": resolution,
                "resolved_at": _now_iso(),
            })
            blockers[i] = resolved_receipt
            found = True
            break

    if not found:
        return None

    # Rewrite the events file atomically
    tmp = events_path.with_suffix(".jsonl.tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        for blocker in blockers:
            handle.write(
                json.dumps(blocker.model_dump(mode="json"), sort_keys=True) + "\n"
            )
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, events_path)

    return resolved_receipt


def load_blockers(
    root: Path | str,
    run_id: str,
) -> tuple[BlockerReceipt, ...]:
    """Load all blockers for a run in append order."""
    return _load_events(
        _run_dir(root, run_id) / BLOCKER_EVENTS_FILE,
        BlockerReceipt,
    )


def blocker_count(
    root: Path | str,
    run_id: str,
) -> int:
    """Count unresolved blockers for a run."""
    blockers = load_blockers(root, run_id)
    return sum(1 for b in blockers if not b.resolved)


# ---------------------------------------------------------------------------
# Handoff operations
# ---------------------------------------------------------------------------

def record_handoff(
    root: Path | str,
    run_id: str,
    receipt: HandoffReceipt,
) -> HandoffReceipt:
    """Persist a handoff to ``handoff-events.jsonl``."""
    run_dir = _run_dir(root, run_id)
    if not run_dir.is_dir():
        raise FileNotFoundError(f"Pipeline run not found: {run_id}")

    events_path = run_dir / HANDOFF_EVENTS_FILE

    # Check for duplicate / idempotent
    if events_path.exists():
        for line in events_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                existing = HandoffReceipt.model_validate_json(line)
            except Exception:
                continue
            if existing.handoff_id == receipt.handoff_id:
                if existing == receipt:
                    return existing
                raise ValueError(
                    f"duplicate handoff id: {receipt.handoff_id}"
                )

    _append_event(events_path, receipt.model_dump(mode="json"))
    return receipt


def update_handoff_acceptance(
    root: Path | str,
    run_id: str,
    handoff_id: str,
    acceptance_status: str,
) -> HandoffReceipt | None:
    """Update a handoff's acceptance status (pending → accepted/rejected)."""
    run_dir = _run_dir(root, run_id)
    events_path = run_dir / HANDOFF_EVENTS_FILE
    if not events_path.is_file():
        return None

    handoffs = list(_load_events(events_path, HandoffReceipt))
    found = False
    updated_receipt: HandoffReceipt | None = None

    for i, handoff in enumerate(handoffs):
        if handoff.handoff_id == handoff_id and handoff.acceptance_status == "pending":
            updated_receipt = handoff.model_copy(update={
                "acceptance_status": acceptance_status,  # type: ignore[arg-type]
            })
            handoffs[i] = updated_receipt
            found = True
            break

    if not found:
        return None

    tmp = events_path.with_suffix(".jsonl.tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        for handoff in handoffs:
            handle.write(
                json.dumps(handoff.model_dump(mode="json"), sort_keys=True) + "\n"
            )
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, events_path)

    return updated_receipt


def load_handoffs(
    root: Path | str,
    run_id: str,
) -> tuple[HandoffReceipt, ...]:
    """Load all handoffs for a run in append order."""
    return _load_events(
        _run_dir(root, run_id) / HANDOFF_EVENTS_FILE,
        HandoffReceipt,
    )


def handoff_count(
    root: Path | str,
    run_id: str,
) -> int:
    """Count pending handoffs for a run."""
    handoffs = load_handoffs(root, run_id)
    return sum(1 for h in handoffs if h.acceptance_status == "pending")


__all__ = [
    "BLOCKER_EVENTS_FILE",
    "HANDOFF_EVENTS_FILE",
    "BlockerReceipt",
    "HandoffReceipt",
    "blocker_count",
    "handoff_count",
    "load_blockers",
    "load_handoffs",
    "record_blocker",
    "record_handoff",
    "resolve_blocker",
    "update_handoff_acceptance",
]
