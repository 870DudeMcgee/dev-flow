from __future__ import annotations

import pytest
from pydantic import ValidationError

from devflow.loop.execution_plan import ExecutionPacket
from devflow.loop.packet_dag import PacketState, ready_packet_ids, validate_packet_dag


def _packets() -> list[ExecutionPacket]:
    return [
        ExecutionPacket(id="packet-b", target_files=["b.py"], depends_on=["packet-a"]),
        ExecutionPacket(id="packet-a", target_files=["a.py"]),
        ExecutionPacket(id="packet-c", target_files=["c.py"], depends_on=["packet-a"]),
    ]


def test_packet_dag_rejects_duplicate_unknown_self_and_cycles() -> None:
    with pytest.raises(ValueError, match="unique"):
        validate_packet_dag([_packets()[1], _packets()[1]])
    with pytest.raises(ValueError, match="unknown"):
        validate_packet_dag([ExecutionPacket(id="a", target_files=["a"], depends_on=["missing"])])
    with pytest.raises(ValidationError, match="itself"):
        ExecutionPacket(id="a", target_files=["a"], depends_on=["a"])
    with pytest.raises(ValueError, match="cycle"):
        validate_packet_dag([
            ExecutionPacket(id="a", target_files=["a"], depends_on=["b"]),
            ExecutionPacket(id="b", target_files=["b"], depends_on=["a"]),
        ])


def test_ready_set_is_sorted_and_only_contains_dependency_satisfied_pending_packets() -> None:
    packets = _packets()
    assert ready_packet_ids(
        packets,
        {"packet-a": PacketState.pending, "packet-b": PacketState.pending, "packet-c": PacketState.pending},
    ) == ("packet-a",)
    assert ready_packet_ids(
        packets,
        {"packet-a": PacketState.succeeded, "packet-b": PacketState.pending, "packet-c": PacketState.pending},
    ) == ("packet-b", "packet-c")
    assert ready_packet_ids(
        packets,
        {"packet-a": PacketState.succeeded, "packet-b": PacketState.succeeded, "packet-c": PacketState.pending},
    ) == ("packet-c",)


def test_ready_set_rejects_missing_extra_or_invalid_packet_states() -> None:
    packets = _packets()
    with pytest.raises(ValueError, match="exactly"):
        ready_packet_ids(packets, {"packet-a": PacketState.pending})
    with pytest.raises(ValueError, match="exactly"):
        ready_packet_ids(packets, {
            "packet-a": PacketState.pending,
            "packet-b": PacketState.pending,
            "packet-c": PacketState.pending,
            "extra": PacketState.pending,
        })
    with pytest.raises(ValueError, match="invalid packet state"):
        ready_packet_ids(packets, {
            "packet-a": "done",
            "packet-b": PacketState.pending,
            "packet-c": PacketState.pending,
        })


def test_failed_dependency_never_becomes_ready() -> None:
    assert ready_packet_ids(
        _packets(),
        {"packet-a": PacketState.failed, "packet-b": PacketState.pending, "packet-c": PacketState.pending},
    ) == ()
