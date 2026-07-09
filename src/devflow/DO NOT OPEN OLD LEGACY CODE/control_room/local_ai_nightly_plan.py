from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from devflow.legacy.control_room.local_model_readiness import load_expected_local_model_manifest

_NIGHTLY_DRY_RUN_TASK_ID = "<task-id>"

def build_local_ai_nightly_dry_run_plan(root: Path) -> dict[str, Any]:
    """Return a deterministic dry-run-only nightly plan with three phases."""
    from devflow.legacy.control_room import local_ai_fleet as _fleet
    manifest = load_expected_local_model_manifest()
    qwen_profile = _fleet._nightly_choose_qwen_profile(manifest)
    scout_target, scout_warnings = _fleet._scout_target(manifest)
    warnings = list(scout_warnings)
    measured_concurrency = _fleet._latest_scout_capacity_concurrency(root)
    effective_concurrency = measured_concurrency if measured_concurrency >= 1 else 1
    if measured_concurrency <= 0:
        warnings.append('Scout capacity is unmeasured. Run `devflow local-ai scout-capacity <wave-file> --dry-run` to measure safe concurrency.')
    else:
        warnings.append(f'Using measured scout capacity concurrency={measured_concurrency}.')
    qwen_server_profile = qwen_profile.get('server_id') or qwen_profile.get('profile_id')
    if not qwen_server_profile:
        warnings.append('No managed local Qwen profile is present in the manifest for dry-run orchestration.')
    if not scout_target.get('manifest_backed'):
        warnings.append('Scout target is not present in the manifest; scout switch will report setup-needed.')
    phases: list[dict[str, Any]] = [{'phase_id': 'qwen-wave', 'title': 'Qwen worker packet phase', 'steps': [{'step_id': 'start_qwen', 'summary': 'Start local Qwen server', 'command': 'devflow local-ai switch supervisor --dry-run --json', 'dry_run': True, 'will_call_model': False, 'scope': 'orchestration'}, {'step_id': 'produce_worker_packets', 'summary': 'Produce Qwen worker packets', 'command': f'devflow task packet {_NIGHTLY_DRY_RUN_TASK_ID} --json', 'dry_run': True, 'will_call_model': False, 'scope': 'packet-generation'}, {'step_id': 'stop_qwen', 'summary': 'Stop local Qwen server', 'command': f'devflow local-model stop {qwen_server_profile} --dry-run --json' if qwen_server_profile else 'devflow local-model stop-all --dry-run --json', 'dry_run': True, 'will_call_model': False, 'scope': 'orchestration'}]}, {'phase_id': 'gemma-wave', 'title': 'Gemma scout wave', 'steps': [{'step_id': 'start_gemma', 'summary': 'Start local Gemma server', 'command': 'devflow local-ai switch scout --dry-run --json', 'dry_run': True, 'will_call_model': False, 'scope': 'orchestration'}, {'step_id': 'run_scout_wave', 'summary': 'Run Gemma scout packet wave', 'command': f'devflow local-ai run-worker-wave <wave-file> --concurrency {effective_concurrency} --dry-run --json', 'dry_run': True, 'will_call_model': False, 'scope': 'scout', 'note': f"Scout target profile: {scout_target.get('label')}"}, {'step_id': 'stop_gemma', 'summary': 'Stop local Gemma server', 'command': 'devflow local-ai stop-all --dry-run --include-ollama --json', 'dry_run': True, 'will_call_model': False, 'scope': 'orchestration'}]}, {'phase_id': 'qwen-review', 'title': 'Qwen review readiness phase', 'steps': [{'step_id': 'restart_qwen_for_review', 'summary': 'Restart local Qwen server for review', 'command': 'devflow local-ai switch supervisor --dry-run --json', 'dry_run': True, 'will_call_model': False, 'scope': 'orchestration'}]}]
    return {'schema_version': 1, 'plan_name': 'nightly-dry-run-local-ai', 'dry_run': True, 'root': str(root.resolve()), 'phases': phases, 'action_count': 7, 'all_dry_run_only': True, 'warnings': warnings}

def render_local_ai_nightly_dry_run_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True)

