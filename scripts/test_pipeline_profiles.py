#!/usr/bin/env python3
"""Pipeline smoke test: run a bounded task through all three profiles.

Runs plan→build→judge→verify for each profile:
  1. legacy-current (Ornith/Qwen/GLM)
  2. hy3-swap (all HY3 via OpenRouter)
  3. gpt-swap (Terra=brainstorm, Luna=verifier+judge, local fleet for build)

Usage:
  PYTHONPATH=src:. .venv/bin/python scripts/test_pipeline_profiles.py [--profile <name>]

Without --profile, runs all three sequentially.
"""

from __future__ import annotations

import json
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

# Ensure src on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from devflow.loop.adapter import create_run_with_state, save_loop_state
from devflow.loop.models import LoopStage
from devflow.loop.execution import (
    run_plan_build_judge,
)
from devflow.loop.routing import (
    set_active_profile,
    describe_routing,
    _reload_all,
)
from devflow.loop.pipeline_run import (
    update_pipeline_run_record,
)

REPO_ROOT = Path(__file__).resolve().parent.parent

# Bounded, source-backed task that exercises planner → build → verify without
# changing production files: builder output is materialized only in the pipeline
# run workspace.
TASK_TOPIC = "Add a utility function `safe_divide(a, b)` to src/devflow/loop/models.py that returns a/b or None if b is zero, and add focused coverage to the existing tests/test_loop_models.py"
TASK_TARGET_FILES = ["src/devflow/loop/models.py", "tests/test_loop_models.py"]
TASK_DOD = (
    "1. safe_divide(a, b) function exists in src/devflow/loop/models.py\n"
    "2. Returns a/b when b != 0\n"
    "3. Returns None when b == 0\n"
    "4. tests/test_loop_models.py includes at least 2 focused safe_divide cases\n"
    "5. The staged target test file passes"
)

PROFILES = ["legacy-current", "hy3-swap", "gpt-swap"]


def run_profile(profile: str) -> dict:
    """Run the bounded task through the pipeline for one profile."""
    print(f"\n{'='*70}")
    print(f"  PROFILE: {profile}")
    print(f"{'='*70}")

    # Set the active profile and reload routing
    set_active_profile(profile)
    _reload_all()

    # Show routing table
    print(f"\nRouting:\n{describe_routing()}")

    # Create a pipeline run
    source = {
        "profile": profile,
        "task": TASK_TOPIC[:100],
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    run_id, state = create_run_with_state(REPO_ROOT, source)
    update_pipeline_run_record(
        REPO_ROOT,
        run_id,
        "readiness-packet.md",
        "\n".join((
            "# Smoke-test repository facts (verified)",
            "- `src/devflow/loop/models.py` already exists and is the requested edit target.",
            "- `tests/test_loop_models.py` already exists and imports its symbols via `from devflow.loop.models import (...)`.",
            "- Add `safe_divide` near the module's top-level helper/model definitions and extend that existing import block with `safe_divide`.",
            "- Stage verification command: `PYTHONPATH=src:. python -m pytest tests/test_loop_models.py -q`.",
            "- Both listed files are existing, writable smoke-test targets; do not create replacement paths.",
        )),
    )
    # Advance to planning_judge stage (what run_planner expects) and enable
    # autonomous verification so the build→judge pass invokes verifier role.
    state = state.model_copy(update={
        "stage": LoopStage.planning_judge,
        "auto_verify": True,
    })
    save_loop_state(REPO_ROOT, state)

    print(f"\nRun ID: {run_id}")

    # Run the full plan→build→judge→verify pipeline
    try:
        result = run_plan_build_judge(
            REPO_ROOT,
            run_id,
            topic=TASK_TOPIC,
            target_files=TASK_TARGET_FILES,
            definition_of_done=TASK_DOD,
            max_planning_rounds=3,
            max_build_rounds=2,
            ensure_lane_on=True,
        )

        # Summarize
        planning_decision = result.get("planning_decision", "unknown")
        build_decision = result.get("decision", "unknown")
        verification = result.get("verification")
        build_cap = result.get("build_cap_exhausted", False)

        summary = {
            "profile": profile,
            "run_id": run_id,
            "planning_decision": planning_decision,
            "build_decision": build_decision,
            "build_cap_exhausted": build_cap,
            "verification_status": (
                verification.status.value if verification else "none"
            ),
            "verification_passed": (
                verification.status.value == "passed" if verification else False
            ),
        }

        print(f"\n--- Result for {profile} ---")
        print(json.dumps(summary, indent=2))

        return summary

    except Exception as exc:
        print(f"\n!!! ERROR in {profile}: {exc}")
        traceback.print_exc()
        return {
            "profile": profile,
            "run_id": run_id,
            "error": str(exc),
            "traceback": traceback.format_exc(),
        }


def main():
    # Allow single profile override
    if "--profile" in sys.argv:
        idx = sys.argv.index("--profile")
        profiles = [sys.argv[idx + 1]]
    else:
        profiles = PROFILES

    results = []
    for profile in profiles:
        result = run_profile(profile)
        results.append(result)

    # Final summary table
    print(f"\n\n{'='*70}")
    print("  PIPELINE TEST SUMMARY")
    print(f"{'='*70}")
    print(f"{'Profile':<20} {'Planning':<15} {'Build':<15} {'Verify':<15} {'Status'}")
    print(f"{'-'*20} {'-'*15} {'-'*15} {'-'*15} {'-'*10}")
    for r in results:
        if "error" in r:
            print(f"{r['profile']:<20} {'ERROR':<15} {'':<15} {'':<15} FAIL")
        else:
            verify = r.get("verification_status", "none")
            status = "PASS" if r.get("verification_passed") else "CHECK"
            planning = str(r.get("planning_decision") or "none")
            build = str(r.get("build_decision") or "none")
            print(f"{r['profile']:<20} {planning:<15} {build:<15} {verify:<15} {status}")

    # Write results JSON
    results_path = REPO_ROOT / ".devflow" / "pipeline-test-results.json"
    results_path.parent.mkdir(parents=True, exist_ok=True)
    with open(results_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nResults written to: {results_path}")

    # Reset to legacy-current
    set_active_profile("legacy-current")


if __name__ == "__main__":
    main()
