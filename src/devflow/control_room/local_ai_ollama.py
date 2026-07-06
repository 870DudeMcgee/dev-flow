from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

_LOCAL_AI_SCOUT_KEEP_ALIVE = "1m"
_LOCAL_AI_SCOUT_START_TIMEOUT_SECONDS = 90.0

def inspect_ollama_loaded_models(*, base_url: str='http://127.0.0.1:11434', timeout_seconds: float=1.0) -> dict[str, Any]:
    """Read Ollama's loaded-model state; the daemon alone is not an active role."""
    from devflow.control_room import local_ai_fleet as _fleet
    url = base_url.rstrip('/') + '/api/ps'
    try:
        with urllib.request.urlopen(url, timeout=timeout_seconds) as response:
            body = response.read().decode('utf-8')
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        return {'status': 'unavailable', 'base_url': base_url, 'loaded_models': [], 'error': str(exc)}
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        return {'status': 'invalid_json', 'base_url': base_url, 'loaded_models': [], 'error': str(exc)}
    models = _fleet._dict_rows(payload.get('models') if isinstance(payload, dict) else None)
    return {'status': 'loaded' if models else 'idle', 'base_url': base_url, 'loaded_models': models}

def inspect_ollama_installed_models(*, base_url: str='http://127.0.0.1:11434', timeout_seconds: float=1.0) -> dict[str, Any]:
    """Read Ollama's installed model list from /api/tags."""
    from devflow.control_room import local_ai_fleet as _fleet
    url = base_url.rstrip('/') + '/api/tags'
    try:
        with urllib.request.urlopen(url, timeout=timeout_seconds) as response:
            body = response.read().decode('utf-8')
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        return {'status': 'unavailable', 'base_url': base_url, 'installed_models': [], 'error': str(exc)}
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        return {'status': 'invalid_json', 'base_url': base_url, 'installed_models': [], 'error': str(exc)}
    models = _fleet._dict_rows(payload.get('models') if isinstance(payload, dict) else None)
    return {'status': 'available' if models else 'empty', 'base_url': base_url, 'installed_models': models}

def start_ollama_model(model_id: str, *, base_url: str='http://127.0.0.1:11434', keep_alive: str=_LOCAL_AI_SCOUT_KEEP_ALIVE, timeout_seconds: float=_LOCAL_AI_SCOUT_START_TIMEOUT_SECONDS) -> dict[str, Any]:
    """Send a tiny request that loads the model into Ollama memory."""
    url = base_url.rstrip('/') + '/api/generate'
    payload: dict[str, Any] = {'model': model_id, 'keep_alive': keep_alive}
    request = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers={'Content-Type': 'application/json'}, method='POST')
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            body = response.read().decode('utf-8')
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        return {'status': 'start_failed', 'provider': 'ollama', 'model': model_id, 'base_url': base_url, 'error': str(exc)}
    if not body.strip():
        return {'status': 'started', 'provider': 'ollama', 'model': model_id, 'base_url': base_url}
    try:
        payload_response = json.loads(body)
    except json.JSONDecodeError as exc:
        return {'status': 'start_failed', 'provider': 'ollama', 'model': model_id, 'base_url': base_url, 'error': str(exc)}
    if payload_response.get('done') is False:
        return {'status': 'start_pending', 'provider': 'ollama', 'model': model_id, 'base_url': base_url}
    return {'status': 'started', 'provider': 'ollama', 'model': model_id, 'base_url': base_url, 'response': payload_response}

