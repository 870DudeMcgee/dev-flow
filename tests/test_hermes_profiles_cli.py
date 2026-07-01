from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from devflow.cli import app
from devflow.control_room import hermes_profiles_command as hermes_profiles_cmd
from devflow.control_room.hermes_profile_resolver import CANONICAL_HERMES_PROFILES


runner = CliRunner()


def _write_profile_config(
    root: Path,
    *,
    profile_id: str,
    provider: str,
    model: str,
    local_base_url: str | None = None,
) -> None:
    path = root / ".hermes" / "profiles" / profile_id / "config.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "model:",
        f"  provider: {provider}",
        f"  default: {model}",
    ]
    if local_base_url is not None:
        lines.append(f"  base_url: {local_base_url}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_stale_hermes_registry(root: Path) -> None:
    registry = root / ".devflow" / "agents" / "registry.yaml"
    registry.parent.mkdir(parents=True, exist_ok=True)
    registry.write_text(
        """version: 1
agents:
  fast_local:
    provider: openrouter
    model: bad-model
    adapter: hermes_profile
    role: frontier_planner_architect_reviewer
    tier: local
    default_mode: frontier_read_only
    workspace: isolated_task_workspace
""",
        encoding="utf-8",
    )


def _write_unresolved_hermes_registry(root: Path) -> None:
    registry = root / ".devflow" / "agents" / "registry.yaml"
    registry.parent.mkdir(parents=True, exist_ok=True)
    registry.write_text(
        """version: 1
agents:
  unknown_hermes_alias:
    provider: local
    model: missing-model
    adapter: hermes_profile
    role: frontier_planner_architect_reviewer
    tier: local
    default_mode: frontier_read_only
    workspace: isolated_task_workspace
""",
        encoding="utf-8",
    )


def test_hermes_profiles_validate_reports_aliases_stale_entries_and_fallback_chain(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", tmp_path.as_posix())

    for profile in CANONICAL_HERMES_PROFILES:
        if profile.id == "hermes-codex-gpt55":
            continue
        _write_profile_config(
            tmp_path,
            profile_id=profile.hermes_profile,
            provider=profile.provider,
            model=profile.model,
            local_base_url="http://127.0.0.1:11434/v1" if profile.provider == "local" else None,
        )

    _write_stale_hermes_registry(tmp_path)

    monkeypatch.setattr(
        hermes_profiles_cmd,
        "_probe_local_endpoint",
        lambda base_url, model, timeout: {"status": "available", "detail": "simulated"},
    )

    result = runner.invoke(app, ["hermes", "profiles", "validate", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)

    assert payload["action"] == "hermes_profiles_validate"
    assert len(payload["canonical_profiles"]) == len(CANONICAL_HERMES_PROFILES)
    assert any(
        item["profile_id"] == "hermes-codex-gpt55" and item["status"] == "setup_required"
        for item in payload["missing_profile_configs"]
    )

    retired = {item["alias"]: item for item in payload["retired_aliases"]}
    assert retired["fast_local"]["canonical_id"] == "hermes-qwen32-latest"

    stale = next(
        item for item in payload["stale_registry_entries"] if item["agent_id"] == "fast_local"
    )
    assert any("id is not a canonical Hermes profile id" in reason for reason in stale["reasons"])
    assert payload["effective_fallback_chain"]["chain"] == ["hermes-codex-gpt55", "hermes-qwen32-latest"]
    assert payload["effective_fallback_chain"]["evaluations"]
    assert any(
        entry["requested_profile_id"] == "hermes-codex-gpt55" and entry["selected_profile_id"] == "hermes-qwen32-latest"
        for entry in payload["effective_fallback_chain"]["evaluations"]
    )


def test_hermes_profiles_validate_reports_unresolved_registry_entries(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", tmp_path.as_posix())
    _write_unresolved_hermes_registry(tmp_path)

    result = runner.invoke(app, ["hermes", "profiles", "validate", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)

    stale = next(
        item for item in payload["stale_registry_entries"] if item["agent_id"] == "unknown_hermes_alias"
    )
    assert stale["config_path"] is None
    assert stale["manual_review_required"] is True
    assert any("does not resolve to a canonical Hermes profile" in reason for reason in stale["reasons"])


def test_hermes_profiles_cleanup_preview_and_apply_record_evidence(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", tmp_path.as_posix())

    for profile in CANONICAL_HERMES_PROFILES:
        if profile.id == "hermes-codex-gpt55":
            continue
        _write_profile_config(
            tmp_path,
            profile_id=profile.hermes_profile,
            provider=profile.provider,
            model=profile.model,
        )

    _write_stale_hermes_registry(tmp_path)

    preview = runner.invoke(app, ["hermes", "profiles", "cleanup", "--preview", "--json"])
    assert preview.exit_code == 0, preview.output
    preview_payload = json.loads(preview.output)
    assert preview_payload["action"] == "hermes_profiles_cleanup_preview"
    assert preview_payload["status"] in {"manual_review_required", "no_action"}
    assert preview_payload["candidate_count"] >= 1

    preview_path = (
        tmp_path
        / ".devflow"
        / "hermes-profile-cleanup"
        / preview_payload["preview_id"]
        / "preview.json"
    )
    assert preview_path.exists()
    evidence_preview = json.loads(preview_path.read_text(encoding="utf-8"))
    assert evidence_preview["action"] == "hermes_profiles_cleanup_preview"
    assert len(evidence_preview["candidates"]) == preview_payload["candidate_count"]

    apply = runner.invoke(
        app,
        ["hermes", "profiles", "cleanup", "--apply", "--preview-id", preview_payload["preview_id"], "--json"],
    )
    assert apply.exit_code == 0, apply.output
    apply_payload = json.loads(apply.output)
    assert apply_payload["action"] == "hermes_profiles_cleanup_apply"
    assert apply_payload["status"] in {"no_action", "applied"}
    assert apply_payload["manual_review_required"] is True

    apply_path = (
        tmp_path
        / ".devflow"
        / "hermes-profile-cleanup"
        / preview_payload["preview_id"]
        / "apply.json"
    )
    assert apply_path.exists()
    evidence_apply = json.loads(apply_path.read_text(encoding="utf-8"))
    assert evidence_apply["status"] == apply_payload["status"]

    rendered_apply = hermes_profiles_cmd.render_hermes_profiles_cleanup_apply(
        tmp_path,
        preview_id=preview_payload["preview_id"],
    )
    assert f"preview_id: {preview_payload['preview_id']}" in rendered_apply
    assert "status: no_action" in rendered_apply


def test_hermes_profiles_cleanup_apply_performs_previewed_safe_rewrite(tmp_path: Path) -> None:
    target = tmp_path / "docs" / "sample.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("use dflocalfast for status\n", encoding="utf-8")

    preview_id = "a" * 32
    preview_path = tmp_path / ".devflow" / "hermes-profile-cleanup" / preview_id / "preview.json"
    preview_path.parent.mkdir(parents=True, exist_ok=True)
    preview_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "action": "hermes_profiles_cleanup_preview",
                "preview_id": preview_id,
                "manual_rewrites": [],
                "safe_rewrites": [
                    {
                        "kind": "replace_text",
                        "path": "docs/sample.md",
                        "old": "dflocalfast",
                        "new": "hermes-qwen32-latest",
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    payload = hermes_profiles_cmd.apply_hermes_profiles_cleanup(tmp_path, preview_id=preview_id)

    assert payload["status"] == "applied"
    assert payload["manual_review_required"] is False
    assert payload["safe_rewrites_applied"] == [
        {"index": 0, "kind": "replace_text", "path": "docs/sample.md"}
    ]
    assert payload["safe_rewrites_blocked"] == []
    assert target.read_text(encoding="utf-8") == "use hermes-qwen32-latest for status\n"


def test_hermes_profiles_cleanup_apply_requires_preview_id(tmp_path: Path) -> None:
    result = CliRunner().invoke(app, ["hermes", "profiles", "cleanup", "--apply", "--json"])
    assert result.exit_code == 1
    assert "--apply requires --preview-id" in result.output


def test_hermes_profiles_cleanup_apply_rejects_unsafe_preview_id(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        app,
        ["hermes", "profiles", "cleanup", "--apply", "--preview-id", "../escape", "--json"],
    )
    assert result.exit_code == 1
    assert "preview_id must be a 32-character lowercase hex id" in result.output
