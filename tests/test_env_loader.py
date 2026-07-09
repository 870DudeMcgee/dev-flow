from __future__ import annotations

import os
from pathlib import Path

import pytest

from devflow.legacy.control_room.env_loader import load_hermes_env_file, resolve_api_key
import devflow.legacy.control_room.env_loader as env_loader_mod


def test_load_hermes_env_file_loads_missing_keys(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# comment line\n"
        "OPENROUTER_API_KEY=sk-or-test-key\n"
        'ANOTHER_KEY="quoted-value"\n'
        "EMPTY_KEY=\n"
        "INVALID-KEY=value\n"
        "no_equals_sign\n"
    )
    os.environ.pop("OPENROUTER_API_KEY", None)
    os.environ.pop("ANOTHER_KEY", None)

    loaded = load_hermes_env_file(env_path=env_file)

    assert "OPENROUTER_API_KEY" in loaded
    assert os.environ.get("OPENROUTER_API_KEY") == "sk-or-test-key"
    assert os.environ.get("ANOTHER_KEY") == "quoted-value"
    assert "INVALID-KEY" not in loaded
    assert "no_equals_sign" not in loaded


def test_load_hermes_env_file_does_not_override_existing(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("OPENROUTER_API_KEY=from-file\n")
    os.environ["OPENROUTER_API_KEY"] = "already-set"

    loaded = load_hermes_env_file(env_path=env_file)

    assert "OPENROUTER_API_KEY" not in loaded
    assert os.environ["OPENROUTER_API_KEY"] == "already-set"


def test_load_hermes_env_file_missing_file_returns_empty(tmp_path: Path) -> None:
    loaded = load_hermes_env_file(env_path=tmp_path / "nonexistent.env")
    assert loaded == {}


def test_resolve_api_key_falls_back_to_hermes_env_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("OPENROUTER_API_KEY=sk-or-fallback\n")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setattr(env_loader_mod, "_HERMES_ENV_PATH", env_file)

    key = resolve_api_key("OPENROUTER_API_KEY")
    assert key == "sk-or-fallback"


def test_resolve_api_key_prefers_os_environ(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("OPENROUTER_API_KEY=from-file\n")
    monkeypatch.setenv("OPENROUTER_API_KEY", "from-env")
    monkeypatch.setattr(env_loader_mod, "_HERMES_ENV_PATH", env_file)

    key = resolve_api_key("OPENROUTER_API_KEY")
    assert key == "from-env"


def test_resolve_api_key_returns_none_when_nowhere(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setattr(env_loader_mod, "_HERMES_ENV_PATH", tmp_path / "nonexistent.env")

    key = resolve_api_key("OPENROUTER_API_KEY")
    assert key is None
