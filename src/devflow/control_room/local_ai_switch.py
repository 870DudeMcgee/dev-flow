from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from devflow.control_room import local_model_server
from devflow.control_room.local_model_readiness import load_expected_local_model_manifest

_LOCAL_AI_SCOUT_KEEP_ALIVE = "1m"
_LOCAL_AI_SCOUT_START_TIMEOUT_SECONDS = 90.0

def build_local_ai_switch(root: Path, role: str, *, dry_run: bool=True) -> dict[str, Any]:
    """Compose the switch payload for supervisor/scout and keep switches side-effect-light by default."""
    from devflow.control_room import local_ai_fleet as _fleet
    requested_role = (role or '').strip().lower()
    if requested_role not in {'supervisor', 'scout'}:
        raise _fleet.LocalAICommandError('Unsupported role. Use one of: supervisor, scout.')
    manifest = load_expected_local_model_manifest()
    scout_runtime: dict[str, Any] | None = None
    scout_installed: dict[str, Any] | None = None
    target_model_for_ollama = None
    if requested_role == 'scout':
        scout_target, _ = _fleet._scout_target(manifest)
        target_model_for_ollama = scout_target.get('model_id')
        scout_base_url = scout_target.get('base_url') or 'http://127.0.0.1:11434'
        scout_runtime = _fleet.inspect_ollama_loaded_models(base_url=scout_base_url)
        scout_installed = _fleet.inspect_ollama_installed_models(base_url=scout_base_url)
    else:
        scout_runtime = _fleet.inspect_ollama_loaded_models()
    loaded_ollama_models = _fleet._dict_rows(scout_runtime.get('loaded_models'))
    loaded_ollama_names = {str(model.get('name')) for model in loaded_ollama_models if isinstance(model.get('name'), str)}
    scout_ready = requested_role == 'scout' and isinstance(target_model_for_ollama, str) and (loaded_ollama_names == {target_model_for_ollama})
    include_ollama = bool(loaded_ollama_names) and (not scout_ready)
    skip_stop_for_unready_scout_apply = requested_role == 'scout' and (not scout_ready) and (not dry_run)
    if skip_stop_for_unready_scout_apply:
        stop_result = {'action': 'stop', 'status': 'skipped', 'processes': []}
    else:
        stop_result = local_model_server.stop_local_model_servers(root, include_ollama=include_ollama, dry_run=dry_run, timeout_seconds=15.0)
    if requested_role == 'supervisor':
        target = _fleet._supervisor_target(manifest)
        target_model = target.get('model_id')
        target_provider = target.get('provider_id')
        target_port = target.get('port')
        if not isinstance(target.get('server_id'), str) or not target.get('server_id'):
            raise _fleet.LocalAICommandError('Supervisor target has no managed local model server.')
        start_result = local_model_server.start_local_model_server(root, target['server_id'], dry_run=dry_run, wait_for_ready=not dry_run)
        started_target = {'status': start_result.get('status'), 'server_id': start_result.get('server'), 'provider': start_result.get('provider'), 'model': start_result.get('model'), 'base_url': start_result.get('base_url'), 'port': start_result.get('port'), 'pid': start_result.get('pid'), 'ready': start_result.get('ready')}
        switch_status = str(start_result.get('status') or 'unknown')
        warnings: list[str] = []
    else:
        target, scout_warnings = _fleet._scout_target(manifest)
        target_model = target.get('model_id')
        target_provider = target.get('provider_id')
        target_port = target.get('port')
        runtime = scout_runtime or _fleet.inspect_ollama_loaded_models(base_url=target.get('base_url') or 'http://127.0.0.1:11434')
        installed = scout_installed or _fleet.inspect_ollama_installed_models(base_url=target.get('base_url') or 'http://127.0.0.1:11434')
        loaded_names = [str(model.get('name')) for model in _fleet._dict_rows(runtime.get('loaded_models')) if isinstance(model.get('name'), str)]
        installed_names = {str(model.get('name')) for model in _fleet._dict_rows(installed.get('installed_models')) if isinstance(model.get('name'), str)}
        warnings = list(scout_warnings)
        warnings.append(f"Ollama runtime status: {runtime.get('status', 'unknown')}.")
        if runtime.get('status') == 'loaded' and loaded_names == [target_model]:
            switch_status = 'ready'
            started_target = {'status': 'ready', 'provider': target_provider, 'model': target_model, 'base_url': target.get('base_url'), 'port': target_port}
        elif target_model in installed_names and (not loaded_names):
            if dry_run:
                switch_status = 'would_start'
                started_target = None
            else:
                start_result = _fleet.start_ollama_model(target_model, base_url=target.get('base_url') or 'http://127.0.0.1:11434', keep_alive=_LOCAL_AI_SCOUT_KEEP_ALIVE, timeout_seconds=_LOCAL_AI_SCOUT_START_TIMEOUT_SECONDS)
                switch_status = str(start_result.get('status') or 'setup_needed')
                if switch_status == 'started':
                    started_target = {'status': switch_status, 'provider': start_result.get('provider'), 'model': start_result.get('model'), 'base_url': start_result.get('base_url'), 'port': target_port}
                else:
                    started_target = None
                    if 'error' in start_result:
                        warnings.append(start_result['error'])
                if not dry_run:
                    warnings.append(f"Scout target '{target_model}' is in Ollama tags; apply is attempting to load it.")
        else:
            switch_status = 'setup_needed'
            started_target = None
            if target_model in loaded_names:
                warnings.append(f"Scout target '{target_model}' is loaded with other Ollama models; unload the other models before switching.")
            else:
                warnings.append(f"Scout target '{target_model}' is not currently available in the Ollama runtime; run it in Ollama before switching.")
            if skip_stop_for_unready_scout_apply:
                warnings.append('No stop was applied because the scout target was not exclusively ready.')
    return {'schema_version': 1, 'action': 'switch', 'status': switch_status, 'role': requested_role, 'dry_run': dry_run, 'apply': not dry_run, 'model': target_model, 'provider': target_provider, 'port': target_port, 'include_ollama_stop': include_ollama, 'stop_skipped': skip_stop_for_unready_scout_apply, 'stopped_targets': _stopped_targets(stop_result), 'started_target': started_target, 'warnings': warnings}

def render_local_ai_switch_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True)

def _stopped_targets(stop_result: dict[str, Any]) -> list[dict[str, Any]]:
    from devflow.control_room import local_ai_fleet as _fleet
    stopped_targets: list[dict[str, Any]] = []
    for process in _fleet._dict_rows(stop_result.get('processes')):
        stopped_targets.append({'pid': process.get('pid'), 'kind': process.get('kind'), 'provider': process.get('provider'), 'model': process.get('model'), 'alias': process.get('alias'), 'port': process.get('port')})
    return stopped_targets

