from __future__ import annotations

import re
from typing import Any, Literal

LoopFamily = Literal["builder_judge", "refactor"]


def _default_status_label(status: str) -> str:
    return re.sub(r"[_-]+", " ", status).title()


def status_label(status: str) -> str:
    return _default_status_label(status)


def loop_phase(name: str, state: str, detail: str = "") -> dict[str, str]:
    return {"name": name, "state": state, "detail": detail}


def loop_artifact(label: str, kind: str, path: str | None, exists: bool) -> dict[str, Any]:
    return {"label": label, "kind": kind, "path": path, "exists": exists}


def loop_envelope(
    *,
    loop_family: LoopFamily,
    run_id: str,
    status: str,
    loop_id: str | None = None,
    status_label: str | None = None,
    phases: list[dict[str, Any]] | None = None,
    artifacts: list[dict[str, Any]] | None = None,
    evidence_path: str | None = None,
    next_safe_action: str = "",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = dict(extra or {})
    payload["loop_family"] = loop_family
    payload["run_id"] = run_id
    payload["status"] = status
    payload["status_label"] = status_label if status_label is not None else _default_status_label(status)
    if loop_id is not None:
        payload["loop_id"] = loop_id
    payload["phases"] = list(phases or [])
    payload["artifacts"] = list(artifacts or [])
    payload["evidence_path"] = evidence_path
    payload["next_safe_action"] = next_safe_action
    return payload
