"""Load API keys from ~/.hermes/.env into os.environ for DevFlow server processes.

The Hermes desktop app stores provider API keys in ~/.hermes/.env, but DevFlow
LaunchAgent / CLI subprocesses do not inherit that file automatically.  This
module parses the file (KEY=VALUE lines, no shell evaluation) and seeds any
missing keys into os.environ so that provider calls inside the operating-layer
server, brainstorm, advisory, and patch workers can find them.
"""

from __future__ import annotations

import os
from pathlib import Path

_HERMES_ENV_PATH = Path.home() / ".hermes" / ".env"


def load_hermes_env_file(env_path: Path | None = None) -> dict[str, str]:
    """Load KEY=VALUE pairs from the Hermes env file into ``os.environ``.

    Existing environment variables are **never overridden** — only keys that
    are absent from the current environment are added.

    Returns a dict of the newly-loaded keys and their values.
    """
    path = env_path or _HERMES_ENV_PATH
    loaded: dict[str, str] = {}
    if not path.exists():
        return loaded
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        key = key.strip()
        if not key or not key.replace("_", "").isalnum():
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        if key not in os.environ:
            os.environ[key] = value
            loaded[key] = value
    return loaded


def resolve_api_key(api_key_env: str) -> str | None:
    """Resolve an API key by env-var name.

    Checks ``os.environ`` first.  If not found, lazily loads
    ``~/.hermes/.env`` and re-checks.  Returns the key value or ``None``.
    """
    value = os.environ.get(api_key_env)
    if value:
        return value
    load_hermes_env_file()
    return os.environ.get(api_key_env)
