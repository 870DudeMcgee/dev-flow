from __future__ import annotations

import json
import sys

from devflow.artifacts import find_artifact, list_artifacts, read_artifact
from devflow.context import build_context_pack, inspect_context_pack, list_context_packs
from devflow.memory import add_memory, inspect_memory, list_memories
from devflow.repo_map import refresh_repo_maps


def artifact_list_command(task_id: str) -> None:
    records = list_artifacts(task_id)
    if not records:
        print(f"No artifacts found for task {task_id}.")
        return

    for record in records:
        metadata = record.metadata
        print(
            f"{record.sequence:03d} {metadata.get('artifact_id', '')} "
            f"{metadata.get('artifact_type', '')} "
            f"role={metadata.get('role', '')} "
            f"created_at={metadata.get('created_at', '')} "
            f"apply={metadata.get('apply_status', '')} "
            f"verify={metadata.get('verification_status', '')}"
        )


def artifact_inspect_command(identifier: str) -> None:
    record = find_artifact(identifier)
    metadata, _ = read_artifact(record.metadata_path)
    print(json.dumps(metadata, indent=2, sort_keys=True))


def context_refresh_command() -> None:
    paths = refresh_repo_maps()
    print("repo maps refreshed")
    for name in ("short", "symbols", "deps"):
        print(f"{name}: {paths[name]}")


def context_build_command(task_file: str, role: str, budget: int | None = None) -> None:
    record = build_context_pack(task_file, role=role, token_budget=budget)
    summary = inspect_context_pack(record.artifact_id)
    print(f"context_pack_id: {summary['context_pack_id']}")
    print(f"artifact_id: {record.artifact_id}")
    print(f"body_path: {record.body_path}")
    print(f"token_estimate: {summary['token_estimate']}/{summary['token_budget']}")


def context_inspect_command(identifier: str) -> None:
    print(json.dumps(inspect_context_pack(identifier), indent=2, sort_keys=True))


def context_list_command(task_id: str) -> None:
    records = list_context_packs(task_id)
    if not records:
        print(f"No context packs found for task {task_id}.")
        return
    for record in records:
        summary = inspect_context_pack(record.artifact_id)
        print(
            f"{record.sequence:03d} {record.artifact_id} "
            f"{summary['context_pack_id']} role={summary['role']} "
            f"tokens={summary['token_estimate']}/{summary['token_budget']}"
        )


def memory_add_command(memory_type: str, statement: str, evidence: str, invalidate_on: list[str]) -> None:
    record = add_memory(
        memory_type=memory_type,
        statement=statement,
        evidence=evidence,
        invalidated_by_paths=invalidate_on,
    )
    print(f"memory_id: {record['memory_id']}")
    print(f"status: {record['status']}")
    print(f"confidence: {record['confidence']}")


def memory_list_command() -> None:
    records = list_memories(include_stale=True)
    if not records:
        print("No devflow memories recorded.")
        return
    for record in records:
        print(
            f"{record.get('memory_id', '')} "
            f"{record.get('status', '')} "
            f"confidence={record.get('confidence', '')} "
            f"type={record.get('type', '')} "
            f"statement={record.get('statement', '')}"
        )


def memory_inspect_command(memory_id: str) -> None:
    try:
        record = inspect_memory(memory_id)
    except FileNotFoundError as exc:
        print(f"Error: {exc}")
        sys.exit(1)
    print(json.dumps(record, indent=2, sort_keys=True))
