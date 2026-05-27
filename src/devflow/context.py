from __future__ import annotations

import fnmatch
import json
import os
from typing import Any

from devflow.artifacts import ArtifactRecord, find_artifact, list_artifacts, read_artifact, write_artifact
from devflow.manager import parse_task_file
from devflow.repo_map import CONTEXT_DIR, refresh_repo_maps


ROLE_DEFAULT_BUDGETS = {
    "cartographer": 4000,
    "reviewer": 6000,
    "implementer": 12000,
    "test_writer": 8000,
    "repair": 4000,
    "summarizer": 3000,
}


def estimate_tokens(text: str) -> int:
    """Estimate tokens using a deterministic four-characters-per-token heuristic."""
    if not text:
        return 0
    return max(1, (len(text) + 3) // 4)


def _repo_head(cwd: str) -> str:
    from devflow.repo_map import _repo_head as repo_head

    return repo_head(cwd)


def _safe_context_id(task_id: str, role: str, sequence: int) -> str:
    safe_task = "".join(char if char.isalnum() or char in "._-" else "_" for char in task_id)
    safe_role = "".join(char if char.isalnum() or char in "._-" else "_" for char in role)
    return f"ctx_{safe_task}_{safe_role}_{sequence:03d}"


def _load_json(path: str) -> dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError as exc:
        raise ValueError(f"Context map is missing: {path}. Run devflow context refresh.") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Context map is invalid JSON: {path}. Run devflow context refresh.") from exc


def _read_text(path: str, limit: int | None = None) -> str:
    with open(path, "r", encoding="utf-8") as handle:
        text = handle.read()
    return text[:limit] if limit is not None else text


def _ensure_repo_maps(cwd: str) -> None:
    required = [
        os.path.join(cwd, CONTEXT_DIR, "repo-map.short.md"),
        os.path.join(cwd, CONTEXT_DIR, "repo-map.symbols.json"),
        os.path.join(cwd, CONTEXT_DIR, "repo-map.deps.json"),
    ]
    if not all(os.path.exists(path) for path in required):
        refresh_repo_maps(cwd)


def _matches_any(path: str, patterns: list[str]) -> bool:
    normalized = path.replace(os.sep, "/")
    for pattern in patterns:
        normalized_pattern = pattern.strip().strip("`").replace(os.sep, "/")
        if normalized == normalized_pattern or fnmatch.fnmatch(normalized, normalized_pattern):
            return True
        if normalized_pattern.endswith("/**") and normalized.startswith(normalized_pattern[:-3]):
            return True
    return False


def _relevant_files(task: dict[str, Any], deps: dict[str, Any]) -> list[str]:
    allowed = [str(item) for item in task.get("allowed_files", []) if str(item).strip()]
    touched = [str(item) for item in task.get("touched_files", []) if str(item).strip()]
    do_not_touch = [str(item) for item in task.get("do_not_touch", []) if str(item).strip()]
    candidates = sorted(deps.get("files", {}).keys())

    if allowed:
        selected = [path for path in candidates if _matches_any(path, allowed)]
    else:
        selected = [path for path in touched if path in deps.get("files", {})]

    for path in touched:
        if path in deps.get("files", {}) and path not in selected:
            selected.append(path)

    blocked = [path for path in selected if _matches_any(path, do_not_touch)]
    return sorted(path for path in selected if path not in blocked)


def _add_section(sections: list[dict[str, Any]], name: str, source: str, content: str, token_budget: int) -> int:
    tokens = estimate_tokens(content)
    used = sum(int(section.get("tokens", 0)) for section in sections)
    remaining = max(0, token_budget - used)
    truncated = False
    if tokens > remaining and remaining > 0:
        max_chars = remaining * 4
        content = content[:max_chars]
        tokens = estimate_tokens(content)
        truncated = True
    elif tokens > remaining:
        return used
    sections.append({"name": name, "source": source, "tokens": tokens, "content": content, "truncated": truncated})
    return used + tokens


def validate_context_pack(pack: dict[str, Any]) -> None:
    """Validate the Phase 2 context pack contract without external dependencies."""
    required = {
        "context_pack_id",
        "task_id",
        "role",
        "token_budget",
        "token_estimate",
        "repo_head",
        "task_contract",
        "sections",
        "allowed_paths",
        "touched_paths",
        "relevant_files",
    }
    missing = sorted(required - set(pack))
    if missing:
        raise ValueError(f"Context pack missing required fields: {', '.join(missing)}")
    if not isinstance(pack["sections"], list):
        raise ValueError("Context pack sections must be a list")
    if int(pack["token_estimate"]) > int(pack["token_budget"]):
        raise ValueError("Context pack exceeds token budget")


def build_context_pack(task_file: str, role: str, token_budget: int | None = None, cwd: str = ".") -> ArtifactRecord:
    """Build a bounded context pack for a task and store it as an artifact."""
    cwd = os.path.abspath(cwd)
    _ensure_repo_maps(cwd)
    token_budget = token_budget or ROLE_DEFAULT_BUDGETS.get(role, ROLE_DEFAULT_BUDGETS["implementer"])

    with open(os.path.join(cwd, task_file), "r", encoding="utf-8") as handle:
        raw_task = handle.read()
    task = parse_task_file(raw_task)
    task_id = str(task.get("task_id", "unknown"))

    short_map_path = os.path.join(cwd, CONTEXT_DIR, "repo-map.short.md")
    symbols_path = os.path.join(cwd, CONTEXT_DIR, "repo-map.symbols.json")
    deps_path = os.path.join(cwd, CONTEXT_DIR, "repo-map.deps.json")
    deps = _load_json(deps_path)
    relevant_files = _relevant_files(task, deps)

    sections: list[dict[str, Any]] = []
    _add_section(sections, "task_contract", task_file, raw_task[:5000], token_budget)
    _add_section(sections, "repo_map", os.path.relpath(short_map_path, cwd).replace(os.sep, "/"), _read_text(short_map_path, limit=4000), token_budget)

    for path in relevant_files:
        full_path = os.path.join(cwd, path)
        if os.path.exists(full_path):
            _add_section(sections, "file_snippet", path, _read_text(full_path, limit=4000), token_budget)
        for test_path in deps.get("files", {}).get(path, {}).get("tested_by", []):
            test_full_path = os.path.join(cwd, test_path)
            if os.path.exists(test_full_path):
                _add_section(sections, "test_mapping", test_path, _read_text(test_full_path, limit=2000), token_budget)

    symbols = _load_json(symbols_path)
    relevant_symbols = [symbol for symbol in symbols.get("symbols", []) if symbol.get("file") in relevant_files]
    if relevant_symbols:
        _add_section(
            sections,
            "symbols",
            os.path.relpath(symbols_path, cwd).replace(os.sep, "/"),
            json.dumps(relevant_symbols, indent=2, sort_keys=True),
            token_budget,
        )

    next_sequence = len([record for record in list_artifacts(task_id) if record.metadata.get("artifact_type") == "context-pack.json"]) + 1
    pack: dict[str, Any] = {
        "context_pack_id": _safe_context_id(task_id, role, next_sequence),
        "task_id": task_id,
        "role": role,
        "token_budget": token_budget,
        "token_estimate": sum(int(section.get("tokens", 0)) for section in sections),
        "repo_head": _repo_head(cwd),
        "task_contract": {
            "title": task.get("title", ""),
            "status": task.get("status", ""),
            "raw_markdown": raw_task[:5000],
        },
        "sections": sections,
        "allowed_paths": task.get("allowed_files", []),
        "touched_paths": task.get("touched_files", []),
        "relevant_files": relevant_files,
    }
    validate_context_pack(pack)
    body = json.dumps(pack, indent=2, sort_keys=True)
    return write_artifact(
        task_id=task_id,
        artifact_type="context-pack.json",
        body=body,
        role="cartographer",
        input_text=raw_task,
        parent_artifacts=[f"task:{task_id}"],
        allowed_paths=list(task.get("allowed_files", [])),
        touched_paths=relevant_files,
        risk="low",
        metadata={"context_pack_id": pack["context_pack_id"], "context_role": role},
        cwd=cwd,
    )


def list_context_packs(task_id: str) -> list[ArtifactRecord]:
    """List context-pack artifacts for a task."""
    return [record for record in list_artifacts(task_id) if record.metadata.get("artifact_type") == "context-pack.json"]


def inspect_context_pack(identifier: str) -> dict[str, Any]:
    """Resolve and summarize a context pack artifact."""
    record = find_artifact(identifier)
    metadata, body = read_artifact(record.metadata_path)
    pack = json.loads(body)
    validate_context_pack(pack)
    return {
        "artifact_id": record.artifact_id,
        "context_pack_id": pack["context_pack_id"],
        "task_id": pack["task_id"],
        "role": pack["role"],
        "token_budget": pack["token_budget"],
        "token_estimate": pack["token_estimate"],
        "sections": len(pack["sections"]),
        "body_path": metadata.get("body_path", record.body_path),
        "metadata_path": metadata.get("metadata_path", record.metadata_path),
    }
