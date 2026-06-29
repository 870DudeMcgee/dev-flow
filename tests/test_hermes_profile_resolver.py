from __future__ import annotations

from pathlib import Path

import pytest

from devflow.control_room.hermes_profile_resolver import (
    CANONICAL_HERMES_PROFILES,
    discover_hermes_profiles,
    resolve_hermes_profile,
    resolve_hermes_profile_for_historical_cleanup,
    resolve_hermes_profile_with_global_fallback,
)


@pytest.mark.parametrize(
    "alias",
    [
        "fast_local",
        "long_local",
        "code_local",
        "dflocalfast",
        "dflocallong",
        "dflocalcode",
        "local-qwen35-mtp",
        "qwen-worker",
        "hermes-profile-dflocalfast",
        "ornith9b",
        "ornith35b",
        "hermes-profile-ornith9b",
        "hermes-profile-ornith35b",
        "dfcodex55",
        "dfminimaxm3",
        "dfqwen37plus",
        "dfqwen37max",
        "dfsonnet46",
        "dfopus48",
    ],
)
def test_discover_hermes_profiles_returns_only_canonical_ids(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, alias: str) -> None:
    monkeypatch.setenv("HOME", tmp_path.as_posix())

    for profile in CANONICAL_HERMES_PROFILES:
        path = tmp_path / ".hermes" / "profiles" / profile.hermes_profile / "config.yaml"
        path.parent.mkdir(parents=True)
        path.write_text(
            f"model:\n  provider: {profile.provider}\n  default: {profile.model}\n",
            encoding="utf-8",
        )

    rows = discover_hermes_profiles()
    row_ids = {row.id for row in rows}
    canonical_ids = {profile.id for profile in CANONICAL_HERMES_PROFILES}

    assert row_ids == canonical_ids
    assert alias not in row_ids
    assert not any(row_id.startswith("hermes-profile-") for row_id in row_ids)


def test_resolve_hermes_profile_only_accepts_canonical_ids(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", tmp_path.as_posix())
    catalog_entry = next(p for p in CANONICAL_HERMES_PROFILES if p.id == "hermes-qwen37plus")
    profile_path = tmp_path / ".hermes" / "profiles" / catalog_entry.hermes_profile / "config.yaml"
    profile_path.parent.mkdir(parents=True)
    profile_path.write_text(
        f"model:\n  provider: {catalog_entry.provider}\n  default: {catalog_entry.model}\n",
        encoding="utf-8",
    )

    canonical_profile = resolve_hermes_profile("hermes-qwen37plus")
    assert canonical_profile is not None
    assert canonical_profile.id == "hermes-qwen37plus"

    assert resolve_hermes_profile("fast_local") is None
    assert resolve_hermes_profile("qwen-worker") is None
    assert resolve_hermes_profile("hermes-profile-dflocalfast") is None


def test_historical_cleanup_helper_resolves_retired_aliases(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", tmp_path.as_posix())

    for profile in CANONICAL_HERMES_PROFILES:
        path = tmp_path / ".hermes" / "profiles" / profile.hermes_profile / "config.yaml"
        path.parent.mkdir(parents=True)
        path.write_text(
            f"model:\n  provider: {profile.provider}\n  default: {profile.model}\n",
            encoding="utf-8",
        )

    alias_resolved = resolve_hermes_profile_for_historical_cleanup("fast_local")
    assert alias_resolved is not None
    assert alias_resolved.id == "hermes-qwen32"

    alias_resolved = resolve_hermes_profile_for_historical_cleanup("hermes-profile-ornith9b")
    assert alias_resolved is not None
    assert alias_resolved.id == "hermes-ornith9b"

    alias_resolved = resolve_hermes_profile_for_historical_cleanup("dfqwen37plus")
    assert alias_resolved is not None
    assert alias_resolved.id == "hermes-qwen37plus"

    canonical_for_cleanup = resolve_hermes_profile_for_historical_cleanup("hermes-qwen37plus")
    assert canonical_for_cleanup is not None
    assert canonical_for_cleanup.id == "hermes-qwen37plus"


def test_global_fallback_prefers_codex_then_qwen32(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", tmp_path.as_posix())

    codex = next(p for p in CANONICAL_HERMES_PROFILES if p.id == "hermes-codex-gpt55")
    qwen32 = next(p for p in CANONICAL_HERMES_PROFILES if p.id == "hermes-qwen32")
    codex_path = tmp_path / ".hermes" / "profiles" / codex.hermes_profile / "config.yaml"
    qwen32_path = tmp_path / ".hermes" / "profiles" / qwen32.hermes_profile / "config.yaml"
    codex_path.parent.mkdir(parents=True)
    codex_path.write_text(
        f"model:\n  provider: {codex.provider}\n  default: {codex.model}\n",
        encoding="utf-8",
    )
    qwen32_path.parent.mkdir(parents=True)
    qwen32_path.write_text(
        f"model:\n  provider: {qwen32.provider}\n  default: {qwen32.model}\n",
        encoding="utf-8",
    )

    resolved = resolve_hermes_profile_with_global_fallback("no-such-profile")
    assert resolved.status == "available"
    assert resolved.profile is not None
    assert resolved.profile.id == "hermes-codex-gpt55"
    assert resolved.to_payload()["selected_profile_id"] == "hermes-codex-gpt55"

    codex_path.unlink()

    resolved = resolve_hermes_profile_with_global_fallback("no-such-profile")
    assert resolved.status == "available"
    assert resolved.profile is not None
    assert resolved.profile.id == "hermes-qwen32"
    assert any("hermes-codex-gpt55" in reason for reason in resolved.failure_reasons)

    resolved = resolve_hermes_profile_with_global_fallback("hermes-codex-gpt55")
    assert resolved.status == "available"
    assert resolved.profile is not None
    assert resolved.profile.id == "hermes-qwen32"
    assert any("hermes-codex-gpt55" in reason for reason in resolved.failure_reasons)

    qwen32_path.unlink()
    resolved = resolve_hermes_profile_with_global_fallback("no-such-profile")
    assert resolved.status == "failed"
    assert resolved.profile is None
    assert resolved.fallback_chain == ("hermes-codex-gpt55", "hermes-qwen32")
    assert any("no-such-profile: not a canonical Hermes profile id" in reason for reason in resolved.failure_reasons)
    assert any("hermes-codex-gpt55" in reason for reason in resolved.failure_reasons)
    assert any("hermes-qwen32" in reason for reason in resolved.failure_reasons)
