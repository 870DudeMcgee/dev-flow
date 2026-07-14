"""Deterministic packet dependency validation and ready-set calculation."""

from __future__ import annotations

from enum import Enum
from typing import Mapping, Sequence

from devflow.loop.execution_plan import ExecutionPacket


class PacketState(str, Enum):
    """Closed host-owned state set used for scheduling readiness."""

    pending = "pending"
    succeeded = "succeeded"
    failed = "failed"


def validate_packet_dag(
    packets: Sequence[ExecutionPacket],
) -> tuple[ExecutionPacket, ...]:
    """Validate packet identities and dependencies, returning stable ID order."""

    by_id: dict[str, ExecutionPacket] = {}
    for packet in packets:
        if packet.id in by_id:
            raise ValueError("packet ids must be unique")
        by_id[packet.id] = packet
    known = set(by_id)
    for packet in packets:
        unknown = set(packet.depends_on) - known
        if unknown:
            raise ValueError(f"unknown packet dependencies: {sorted(unknown)!r}")

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(packet_id: str) -> None:
        if packet_id in visiting:
            raise ValueError("packet dependency graph contains a cycle")
        if packet_id in visited:
            return
        visiting.add(packet_id)
        for dependency in by_id[packet_id].depends_on:
            visit(dependency)
        visiting.remove(packet_id)
        visited.add(packet_id)

    for packet_id in sorted(by_id):
        visit(packet_id)
    return tuple(by_id[packet_id] for packet_id in sorted(by_id))


def ready_packet_ids(
    packets: Sequence[ExecutionPacket],
    states: Mapping[str, PacketState | str],
) -> tuple[str, ...]:
    """Return the stable ready set for an exact validated state projection."""

    ordered = validate_packet_dag(packets)
    expected = {packet.id for packet in ordered}
    if set(states) != expected:
        raise ValueError("packet states must cover exactly the packet DAG")
    normalized: dict[str, PacketState] = {}
    for packet_id, value in states.items():
        try:
            normalized[packet_id] = PacketState(value)
        except ValueError as exc:
            raise ValueError(f"invalid packet state for {packet_id!r}: {value!r}") from exc
    return tuple(
        packet.id
        for packet in ordered
        if normalized[packet.id] is PacketState.pending
        and all(
            normalized[dependency] is PacketState.succeeded
            for dependency in packet.depends_on
        )
    )


__all__ = ["PacketState", "ready_packet_ids", "validate_packet_dag"]
