#!/usr/bin/env python3
"""Persisted transport smoke for routable roles without native stage executors."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from devflow.loop.adapter import create_run_with_state
from devflow.loop.execution import run_role
from devflow.loop.pipeline_run import update_pipeline_run_record
from devflow.loop.routing import _reload_all, resolve_role, set_active_profile

PROFILE = sys.argv[1] if len(sys.argv) > 1 else "gpt-swap"


def main() -> None:
    set_active_profile(PROFILE)
    _reload_all()
    run_id, _ = create_run_with_state(
        ROOT,
        {
            "profile": PROFILE,
            "kind": "routable-role-smoke",
            "started_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    results: dict[str, dict[str, str]] = {}
    calls = {
        "brainstorm": (
            "You are the DevFlow brainstorm role. Return only JSON with keys "
            "idea, ambiguity, and next_step.",
            "Assess this bounded request: add safe_divide(a, b) that returns None for zero denominator.",
        ),
        "final_judge": (
            "You are the DevFlow final judge. Return only JSON with keys "
            "status and rationale.",
            "Evidence: safe_divide is implemented; four focused tests passed; the build judge approved. "
            "Return passed if this evidence is sufficient.",
        ),
    }
    for role, (system_prompt, user_prompt) in calls.items():
        slot = resolve_role(role)
        result = run_role(
            ROOT,
            role=role,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            task_id=run_id,
            worker_id="routable-role-smoke",
            ensure_lane_on=True,
        )
        if not result.content.strip():
            raise RuntimeError(f"{role} returned empty content")
        results[role] = {
            "model": result.model,
            "content": result.content.strip()[:2000],
            "transport": slot.transport,
        }

    update_pipeline_run_record(ROOT, run_id, "routable-role-smoke.json", results)
    print(json.dumps({"run_id": run_id, "profile": PROFILE, "roles": results}, indent=2))


if __name__ == "__main__":
    main()
