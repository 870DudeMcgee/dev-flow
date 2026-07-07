from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from devflow.control_room.paths import relative_path
from devflow.control_room.persistence import atomic_write_text
from devflow.control_room.task_packet import _redact_secrets_in_value, _redact_string


DEFAULT_RUN_ID = "ornith-35b-20260701"
DEFAULT_MAX_EXAMPLES = 500
MAX_FILE_BYTES = 200_000
MAX_EXCERPT_CHARS = 4_000
MAX_TASK_EVENTS = 8
MAX_DOC_EXCERPTS_PER_FILE = 8
MAX_REPORT_FILES = 24
SYSTEM_PROMPT = (
    "You are a grounded local-first Dev-Flow and Hermes assistant. "
    "Use only bounded local evidence. Do not invent provider calls, "
    "training execution, publishing, pushing, or unsafe actions."
)
DOC_PATHS = (
    "AGENTS.md",
    "README.md",
    "docs/DEVFLOW_SOURCE_OF_TRUTH.md",
    "docs/README.md",
    "docs/local-worker-policy.md",
    "docs/verification-ledger.md",
)
HARD_STOPS = [
    "local_only_export",
    "no_training_execution",
    "no_provider_calls",
    "no_push",
    "no_publish",
    "no_remote_job_submission",
    "no_torch_or_unsloth_runtime",
]
LORA_SETTINGS = {
    "source": "handoff_2026-07-01",
    "max_seq_length": 2048,
    "per_device_train_batch_size": 1,
    "gradient_accumulation_steps": 4,
    "rank": 16,
    "checkpoint_steps": "100-250",
    "text_only": True,
    "full_fine_tune": False,
}


def prepare_ornith_training_dataset(
    root: Path,
    *,
    run_id: str = DEFAULT_RUN_ID,
    max_examples: int = DEFAULT_MAX_EXAMPLES,
) -> dict[str, Any]:
    repo_root = root.resolve()
    run_dir = repo_root / ".devflow" / "training" / run_id
    dataset_path = run_dir / "dataset.jsonl"
    manifest_path = run_dir / "manifest.json"
    dry_run_path = run_dir / "remote-training-dry-run.json"

    examples = _collect_examples(repo_root)
    if max_examples >= 0:
        examples = examples[:max_examples]
    source_counts = dict(sorted(Counter(row["metadata"]["source_kind"] for row in examples).items()))

    lines = [json.dumps(_sanitize_row(row), sort_keys=True) for row in examples]
    dataset_body = "".join(f"{line}\n" for line in lines)
    redaction = _redaction_report(dataset_body)
    atomic_write_text(dataset_path, dataset_body)
    dataset_sha256 = hashlib.sha256(dataset_body.encode("utf-8")).hexdigest()

    warnings: list[str] = []
    if len(examples) < 500:
        warnings.append("fewer than 500 examples collected; smoke-only dataset")
    warnings.append("dry-run only: remote NVIDIA environment required for real training")
    warnings.append("publish and push are disabled")
    if redaction["status"] != "pass":
        warnings.append("post-redaction secret scan failed; do not use this dataset for training")

    manifest = _redact_secrets_in_value(
        {
            "status": "blocked" if redaction["status"] != "pass" else "dry_run_ready",
            "run_id": run_id,
            "example_count": len(examples),
            "source_counts": source_counts,
            "dataset_sha256": dataset_sha256,
            "redaction": redaction,
            "output_paths": {
                "dataset_jsonl": relative_path(repo_root, dataset_path),
                "manifest_json": relative_path(repo_root, manifest_path),
                "remote_training_dry_run_json": relative_path(repo_root, dry_run_path),
            },
            "hard_stops": HARD_STOPS,
            "warnings": warnings,
            "max_examples": max_examples,
            "dataset_format": "messages-jsonl",
        }
    )
    atomic_write_text(manifest_path, json.dumps(manifest, indent=2, sort_keys=True) + "\n")

    dry_run_manifest = _redact_secrets_in_value(
        {
            "run_id": run_id,
            "dataset_path": relative_path(repo_root, dataset_path),
            "manifest_path": relative_path(repo_root, manifest_path),
            "remote_runtime_requirement": "NVIDIA-backed environment required for real training",
            "model_candidates": [
                "Jackrong/Ornith3.6-35B-A3B-v1-GGUF",
                "lmstudio-community/Ornith3.6-35B-A3B-MLX-4bit",
            ],
            "lora": LORA_SETTINGS,
            "publish_disabled": True,
            "push_disabled": True,
            "provider_calls_disabled": True,
            "training_execution_disabled": True,
            "redaction": redaction,
            "hard_stops": HARD_STOPS,
            "warnings": warnings,
        }
    )
    atomic_write_text(dry_run_path, json.dumps(dry_run_manifest, indent=2, sort_keys=True) + "\n")

    return {
        "run_id": run_id,
        "example_count": len(examples),
        "source_counts": source_counts,
        "dataset_sha256": dataset_sha256,
        "redaction": redaction,
        "output_paths": manifest["output_paths"],
        "warnings": warnings,
        "hard_stops": HARD_STOPS,
    }


def _collect_examples(root: Path) -> list[dict[str, Any]]:
    examples: list[dict[str, Any]] = []
    examples.extend(_task_examples(root))
    examples.extend(_brainstorm_examples(root))
    examples.extend(_doc_examples(root))
    examples.extend(_report_examples(root))
    return examples


def _task_examples(root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    tasks_dir = root / ".devflow" / "tasks"
    if not tasks_dir.exists():
        return rows
    for task_dir in sorted(path for path in tasks_dir.iterdir() if path.is_dir()):
        summary_path = task_dir / "summary.json"
        events_path = task_dir / "events.jsonl"
        if summary_path.exists():
            payload = _load_json(summary_path)
            summary = payload.get("summary") if isinstance(payload, dict) else None
            if isinstance(summary, str) and summary.strip():
                user_payload = {
                    "task_id": payload.get("task_id"),
                    "title": payload.get("title"),
                    "status": payload.get("status"),
                    "merge_ready": payload.get("merge_ready"),
                }
                rows.append(
                    _make_row(
                        "task_summary",
                        relative_path(root, summary_path),
                        [
                            {"role": "system", "content": SYSTEM_PROMPT},
                            {
                                "role": "user",
                                "content": _bounded_text(
                                    "Summarize this task state from local evidence:\n"
                                    + json.dumps(user_payload, indent=2, sort_keys=True)
                                ),
                            },
                            {"role": "assistant", "content": _bounded_text(summary)},
                        ],
                    )
                )
        if events_path.exists():
            events = _load_jsonl(events_path)
            if events:
                rows.append(
                    _make_row(
                        "task_events",
                        relative_path(root, events_path),
                        [
                            {"role": "system", "content": SYSTEM_PROMPT},
                            {
                                "role": "user",
                                "content": "Return the bounded task event excerpt for grounding review.",
                            },
                            {
                                "role": "assistant",
                                "content": _bounded_text(
                                    json.dumps(events[-MAX_TASK_EVENTS:], indent=2, sort_keys=True)
                                ),
                            },
                        ],
                    )
                )
    return rows


def _brainstorm_examples(root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    brainstorm_dir = root / ".devflow" / "brainstorms"
    if not brainstorm_dir.exists():
        return rows
    for transcript_path in sorted(brainstorm_dir.glob("*/transcript.jsonl")):
        messages = [
            item
            for item in _load_jsonl(transcript_path)
            if isinstance(item, dict)
            and item.get("kind") == "message"
            and item.get("role") in {"user", "assistant"}
            and isinstance(item.get("content"), str)
        ]
        for index in range(len(messages) - 1):
            left = messages[index]
            right = messages[index + 1]
            if left.get("role") != "user" or right.get("role") != "assistant":
                continue
            rows.append(
                _make_row(
                    "brainstorm_transcript",
                    relative_path(root, transcript_path),
                    [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": _bounded_text(left["content"])},
                        {"role": "assistant", "content": _bounded_text(right["content"])},
                    ],
                    pair_index=index,
                )
            )
    return rows


def _doc_examples(root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    doc_paths = [root / rel for rel in DOC_PATHS]
    doc_paths.extend(sorted((root / "docs" / "integrations").glob("hermes*.md")))
    for path in doc_paths:
        if not path.exists() or not path.is_file():
            continue
        text = _safe_file_text(path)
        if not text:
            continue
        for index, excerpt in enumerate(_chunk_text(text, MAX_EXCERPT_CHARS, MAX_DOC_EXCERPTS_PER_FILE)):
            rows.append(
                _make_row(
                    "doc_excerpt",
                    relative_path(root, path),
                    [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {
                            "role": "user",
                            "content": (
                                f"Review this bounded reference excerpt from {relative_path(root, path)} "
                                "and return it verbatim for local grounding:\n\n"
                                f"{excerpt}"
                            ),
                        },
                        {"role": "assistant", "content": excerpt},
                    ],
                    excerpt_index=index,
                )
            )
    return rows


def _report_examples(root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    report_paths = sorted(_iter_safe_report_paths(root))[:MAX_REPORT_FILES]
    for report_path in report_paths:
        text = _safe_file_text(report_path)
        if not text:
            continue
        rows.append(
            _make_row(
                "report_excerpt",
                relative_path(root, report_path),
                [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": f"Return the bounded local report excerpt from {relative_path(root, report_path)}.",
                    },
                    {"role": "assistant", "content": _bounded_text(text)},
                ],
            )
        )
    return rows


def _iter_safe_report_paths(root: Path) -> list[Path]:
    devflow_dir = root / ".devflow"
    if not devflow_dir.exists():
        return []
    paths: list[Path] = []
    for path in devflow_dir.rglob("*"):
        if not path.is_file():
            continue
        rel = relative_path(root, path)
        parts = path.parts
        if any(part in {"workspaces", "cache", "caches", "logs", "graphify-out", "__pycache__"} for part in parts):
            continue
        if any(token in rel for token in ("raw_output", "response.raw", "prompt.", "spec.raw", ".env")):
            continue
        if path.name not in {"report.md", "report.json"} and not path.name.startswith("report."):
            continue
        paths.append(path)
    return paths


def _safe_file_text(path: Path) -> str:
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            return ""
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return _bounded_text(text)


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _load_jsonl(path: Path) -> list[Any]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    payload: list[Any] = []
    for line in lines:
        if not line.strip():
            continue
        try:
            payload.append(json.loads(line))
        except ValueError:
            continue
    return payload


def _chunk_text(text: str, size: int, max_chunks: int) -> list[str]:
    clean = _bounded_text(text, max_chars=size * max_chunks)
    if not clean:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(clean) and len(chunks) < max_chunks:
        chunks.append(clean[start:start + size])
        start += size
    return [chunk for chunk in chunks if chunk.strip()]


def _bounded_text(text: str, *, max_chars: int = MAX_EXCERPT_CHARS) -> str:
    redacted = _redact_string(text)
    clipped = redacted[:max_chars]
    if _contains_obvious_secret(clipped):
        return ""
    return clipped.strip()


def _make_row(
    source_kind: str,
    source_path: str,
    messages: list[dict[str, str]],
    **metadata: Any,
) -> dict[str, Any]:
    row = {
        "messages": messages,
        "metadata": {
            "source_kind": source_kind,
            "source_path": source_path,
            **metadata,
        },
    }
    return _sanitize_row(row)


def _sanitize_row(row: dict[str, Any]) -> dict[str, Any]:
    sanitized = _redact_secrets_in_value(row)
    if _contains_obvious_secret(json.dumps(sanitized, sort_keys=True)):
        sanitized["messages"] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": "Sensitive source withheld during training export."},
            {"role": "assistant", "content": "Source omitted after redaction guard."},
        ]
    return sanitized


def _contains_obvious_secret(text: str) -> bool:
    return bool(_secret_findings(text))


def _redaction_report(text: str) -> dict[str, Any]:
    findings = _secret_findings(text)
    return {
        "status": "blocked" if findings else "pass",
        "post_redaction_secret_findings": findings,
        "redaction_markers": text.count("[REDACTED"),
    }


def _secret_findings(text: str) -> list[str]:
    findings = []
    if re.search(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{12,}\b", text):
        findings.append("openai_key")
    if re.search(r"\bghp_[A-Za-z0-9]{20,}\b", text):
        findings.append("github_token")
    if re.search(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b", text):
        findings.append("github_pat")
    if "-----BEGIN" in text:
        findings.append("private_key_block")
    return sorted(set(findings))
