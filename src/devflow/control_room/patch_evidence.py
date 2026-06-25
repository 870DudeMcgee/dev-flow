from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def read_patch_application_evidence(task_path: Path) -> dict[str, Any] | None:
    path = task_path / "patch-application.json"
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None
