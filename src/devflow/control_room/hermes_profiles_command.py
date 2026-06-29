from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
import uuid

import typer

from devflow.control_room.agent_registry import load_agent_registry
from devflow.control_room.hermes_profile_resolver import (
    CANONICAL_HERMES_PROFILES,
    CANONICAL_PROFILE_IDS,
    HERMES_GLOBAL_FALLBACK_IDS,
    HERMES_RETIRED_ALIAS_TO_CANONICAL_ID,
    discover_hermes_profiles,
    resolve_hermes_profile,
    resolve_hermes_profile_for_historical_cleanup,
    resolve_hermes_profile_with_global_fallback,
)
from devflow.control_room.persistence import atomic_write_text, utc_now
from devflow.control_room.paths import relative_path


SCHEMA_VERSION = 1
SAFE_PREVIEW_ID = re.compile(r"^[a-f0-9]{32}$")

hermes_profiles_app = typer.Typer(help="Inspect and clean Hermes profile registrations")


def build_hermes_profiles_validation(root: Path, *, endpoint_timeout: float = 0.4) -> dict[str, Any]:
    canonical_rows = discover_hermes_profiles()
    canonical_map = {row.id: row for row in canonical_rows}
    validate_profile_rows = [_serialize_profile_row(row, timeout=endpoint_timeout) for row in canonical_rows]

    missing_profiles = [
        {
            "profile_id": row["id"],
            "hermes_profile": row["hermes_profile"],
            "config_path": row["config_path"],
            "status": row["status"],
            "detail": row["blocked_reason"],
        }
        for row in validate_profile_rows
        if row["config_exists"] is False
    ]

    retired_aliases = _build_retired_aliases(canonical_map)
    stale_registry_entries = _collect_stale_registry_entries(root)
    fallback_chains = [
        resolve_hermes_profile_with_global_fallback(profile_id).to_payload()
        for profile_id in sorted(CANONICAL_PROFILE_IDS)
    ]

    return {
        "schema_version": SCHEMA_VERSION,
        "action": "hermes_profiles_validate",
        "generated_at": utc_now().isoformat(),
        "repo_root": str(root.resolve()),
        "canonical_profiles": validate_profile_rows,
        "retired_aliases": retired_aliases,
        "missing_profile_configs": missing_profiles,
        "stale_registry_entries": stale_registry_entries,
        "effective_fallback_chain": {
            "chain": list(HERMES_GLOBAL_FALLBACK_IDS),
            "evaluations": fallback_chains,
        },
    }


def render_hermes_profiles_validate(root: Path, *, json_output: bool = False) -> str:
    payload = build_hermes_profiles_validation(root)
    if json_output:
        return json.dumps(payload, indent=2, sort_keys=True) + "\n"

    lines = [
        "Hermes Profile Validation",
        f"canonical_profiles: {len(payload['canonical_profiles'])}",
        f"retired_aliases: {len(payload['retired_aliases'])}",
        f"missing_profile_configs: {len(payload['missing_profile_configs'])}",
        f"stale_registry_entries: {len(payload['stale_registry_entries'])}",
        "",
        "Canonical Profiles",
    ]
    for row in payload["canonical_profiles"]:
        lines.append(f"- {row['id']}: {row['status']} ({row['endpoint_status']})")
    lines.extend(["", "Retired Aliases"])
    for row in payload["retired_aliases"]:
        lines.append(f"- {row['alias']} -> {row['canonical_id']}")
    lines.extend(["", "Fallback Chain", f"chain: {', '.join(payload['effective_fallback_chain']['chain'])}"])
    return "\n".join(lines) + "\n"


def build_hermes_profiles_cleanup_preview(root: Path) -> dict[str, Any]:
    validation = build_hermes_profiles_validation(root)
    missing_configs = validation["missing_profile_configs"]
    stale_entries = validation["stale_registry_entries"]

    candidates = [
        {
            "kind": "missing_profile_config",
            "profile_id": item["profile_id"],
            "detail": item["detail"],
            "manual_remedy": f"Recreate {item['config_path']}",
        }
        for item in missing_configs
    ] + [
        {
            **item,
            "manual_remedy": _remedy_for_stale_entry(item),
        }
        for item in stale_entries
    ]

    preview_id = uuid.uuid4().hex
    preview_path = cleanup_dir(root) / preview_id / "preview.json"
    manual_rewrites = list(candidates)
    safe_rewrites: list[dict[str, Any]] = []
    status = "manual_review_required" if manual_rewrites else "no_action"
    atomic_write_text(
        preview_path,
        json.dumps(
            {
                "schema_version": SCHEMA_VERSION,
                "action": "hermes_profiles_cleanup_preview",
                "preview_id": preview_id,
                "generated_at": utc_now().isoformat(),
                "candidates": candidates,
                "manual_rewrites": manual_rewrites,
                "safe_rewrites": safe_rewrites,
                "status": status,
                "manual_review_required": bool(manual_rewrites),
                "preview_path": relative_path(root, preview_path),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "action": "hermes_profiles_cleanup_preview",
        "preview_id": preview_id,
        "generated_at": utc_now().isoformat(),
        "preview_path": relative_path(root, preview_path),
        "status": status,
        "manual_review_required": bool(manual_rewrites),
        "candidate_count": len(candidates),
    }


def render_hermes_profiles_cleanup_preview(root: Path, *, json_output: bool = False) -> str:
    payload = build_hermes_profiles_cleanup_preview(root)
    if json_output:
        return json.dumps(payload, indent=2, sort_keys=True) + "\n"
    lines = [
        "Hermes Profile Cleanup Preview",
        f"preview_id: {payload['preview_id']}",
        f"status: {payload['status']}",
        f"preview_path: {payload['preview_path']}",
        f"candidate_count: {payload['candidate_count']}",
        "",
        "Next step:",
        f"devflow hermes profiles cleanup --apply --preview-id {payload['preview_id']}",
    ]
    return "\n".join(lines) + "\n"


def apply_hermes_profiles_cleanup(root: Path, *, preview_id: str) -> dict[str, Any]:
    preview_path = _preview_path(root, preview_id)
    if not preview_path.exists():
        raise ValueError(f"preview not found: {preview_path}")

    preview = _read_json_object(preview_path)
    if not isinstance(preview, dict) or preview.get("action") != "hermes_profiles_cleanup_preview":
        raise ValueError("invalid preview payload")

    apply_path = preview_path.parent / "apply.json"
    safe_rewrites = preview.get("safe_rewrites") if isinstance(preview.get("safe_rewrites"), list) else []
    applied_safe_rewrites, blocked_safe_rewrites = _apply_safe_rewrites(root, safe_rewrites)
    if applied_safe_rewrites and blocked_safe_rewrites:
        status = "partial"
    elif blocked_safe_rewrites:
        status = "blocked"
    elif applied_safe_rewrites:
        status = "applied"
    else:
        status = "no_action"

    manual_rewrites = preview.get("manual_rewrites") if isinstance(preview.get("manual_rewrites"), list) else []
    manual_review_required = bool(manual_rewrites or blocked_safe_rewrites)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "action": "hermes_profiles_cleanup_apply",
        "preview_id": preview_id,
        "started_at": utc_now().isoformat(),
        "status": status,
        "manual_review_required": manual_review_required,
        "safe_rewrites_applied": applied_safe_rewrites,
        "safe_rewrites_blocked": blocked_safe_rewrites,
        "manual_rewrites_blocked": manual_rewrites,
        "apply_path": relative_path(root, apply_path),
    }
    atomic_write_text(
        apply_path,
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
    )
    return payload


def render_hermes_profiles_cleanup_apply(root: Path, *, preview_id: str, json_output: bool = False) -> str:
    payload = build_hermes_profiles_cleanup_apply(root, preview_id=preview_id)
    if json_output:
        return json.dumps(payload, indent=2, sort_keys=True) + "\n"
    lines = [
        "Hermes Profile Cleanup Apply",
        f"preview_id: {payload['preview_id']}",
        f"status: {payload['status']}",
        f"manual_review_required: {payload['manual_review_required']}",
        f"apply_path: {payload['apply_path']}",
    ]
    return "\n".join(lines) + "\n"


def build_hermes_profiles_cleanup_apply(root: Path, *, preview_id: str) -> dict[str, Any]:
    return apply_hermes_profiles_cleanup(root, preview_id=preview_id)


def _serialize_profile_row(profile: Any, *, timeout: float) -> dict[str, Any]:
    endpoint_status = _local_endpoint_status(profile, timeout=timeout)
    return {
        "id": profile.id,
        "label": profile.label,
        "hermes_profile": profile.hermes_profile,
        "provider": profile.provider,
        "model": profile.model,
        "base_url": profile.base_url,
        "config_path": str(profile.config_path),
        "status": profile.status,
        "config_exists": profile.config_path.exists(),
        "blocked_reason": profile.blocked_reason,
        "key_env": profile.key_env,
        "key_status": profile.key_status,
        "key_source": profile.key_source,
        "endpoint_status": endpoint_status["status"],
        "endpoint_detail": endpoint_status.get("detail"),
        "selectable": profile.id in CANONICAL_PROFILE_IDS and profile.status == "available",
    }


def _local_endpoint_status(profile: Any, *, timeout: float) -> dict[str, Any]:
    if profile.base_url is None:
        return {"status": "not_checked", "detail": "no base_url configured"}
    if not _is_local_http_base_url(profile.base_url):
        return {"status": "not_checked", "detail": "non-local endpoint"}
    return _probe_local_endpoint(profile.base_url, profile.model, timeout=timeout)


def _is_local_http_base_url(base_url: str | None) -> bool:
    if base_url is None or not base_url.strip():
        return False
    parsed = urlparse(base_url)
    return parsed.scheme in {"http", "https"} and parsed.hostname in {"127.0.0.1", "localhost", "::1"}


def _probe_local_endpoint(base_url: str, model: str, *, timeout: float) -> dict[str, Any]:
    models_url = _normalize_models_url(base_url)
    try:
        request = urllib.request.Request(models_url, method="GET", headers={"accept": "application/json"})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read(4096).decode("utf-8"))
            available_models = _extract_model_ids(payload)
            if model in available_models:
                return {"status": "available", "detail": "endpoint reachable"}
            if available_models:
                return {
                    "status": "missing_model",
                    "detail": f"model '{model}' is not listed by endpoint",
                }
            return {
                "status": "unavailable",
                "detail": "endpoint responded without model list",
            }
    except urllib.error.URLError as exc:
        return {"status": "unavailable", "detail": f"unreachable endpoint ({exc})"}
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        return {"status": "unavailable", "detail": str(exc)}


def _normalize_models_url(base_url: str) -> str:
    cleaned = base_url.rstrip("/")
    if cleaned.endswith("/v1"):
        return f"{cleaned}/models"
    return f"{cleaned}/v1/models"


def _extract_model_ids(payload: Any) -> set[str]:
    rows = []
    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, list):
            rows.extend(_extract_model_item_model(item) for item in data)
        else:
            models = payload.get("models")
            if isinstance(models, list):
                rows.extend(_extract_model_item_model(item) for item in models)
    return {row for row in rows if row}


def _extract_model_item_model(item: Any) -> str | None:
    if isinstance(item, dict):
        value = item.get("id") or item.get("model")
        if isinstance(value, str):
            return value
    return None


def _build_retired_aliases(canonical_map: dict[str, Any]) -> list[dict[str, Any]]:
    retired_aliases: list[dict[str, Any]] = []
    for alias in sorted(HERMES_RETIRED_ALIAS_TO_CANONICAL_ID):
        canonical_id = HERMES_RETIRED_ALIAS_TO_CANONICAL_ID[alias]
        retired_aliases.append(
            {
                "alias": alias,
                "canonical_id": canonical_id,
                "canonical_profile_exists": canonical_id in canonical_map,
                "resolved_profile": resolve_hermes_profile_for_historical_cleanup(alias) is not None,
            }
        )
    return retired_aliases


def _collect_stale_registry_entries(root: Path) -> list[dict[str, Any]]:
    try:
        registry = load_agent_registry(root)
    except Exception as exc:
        return [{"kind": "registry_load_error", "detail": str(exc)}]

    stale: list[dict[str, Any]] = []
    for agent in registry.agents.values():
        if agent.adapter != "hermes_profile":
            continue
        reasons: list[str] = []
        canonical = resolve_hermes_profile(agent.id) or resolve_hermes_profile_for_historical_cleanup(agent.id)
        if agent.id not in CANONICAL_PROFILE_IDS:
            reasons.append("id is not a canonical Hermes profile id")
        if canonical is None:
            reasons.append("entry does not resolve to a canonical Hermes profile")
            stale.append(
                {
                    "agent_id": agent.id,
                    "provider": agent.provider,
                    "model": agent.model,
                    "config_path": None,
                    "reasons": reasons,
                    "manual_review_required": True,
                }
            )
            continue
        if agent.provider != canonical.provider:
            reasons.append(f"provider mismatch (registry={agent.provider} catalog={canonical.provider})")
        if agent.model != canonical.model:
            reasons.append(f"model mismatch (registry={agent.model} catalog={canonical.model})")
        if canonical.config_path is not None and not canonical.config_path.exists():
            reasons.append("catalog config missing")
        if reasons:
            stale.append(
                {
                    "agent_id": agent.id,
                    "provider": agent.provider,
                    "model": agent.model,
                    "config_path": str(canonical.config_path),
                    "reasons": reasons,
                    "manual_review_required": True,
                }
            )
    return stale


def _apply_safe_rewrites(root: Path, safe_rewrites: list[Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    applied: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    for index, rewrite in enumerate(safe_rewrites):
        if not isinstance(rewrite, dict):
            blocked.append({"index": index, "reason": "rewrite must be an object"})
            continue

        action = str(rewrite.get("kind") or rewrite.get("action") or "").strip()
        if action != "replace_text":
            blocked.append(
                {
                    "index": index,
                    "kind": action or None,
                    "path": rewrite.get("path"),
                    "reason": "unsupported safe rewrite kind",
                }
            )
            continue

        path_value = rewrite.get("path")
        old_text = rewrite.get("old")
        new_text = rewrite.get("new")
        if not isinstance(path_value, str) or not path_value.strip():
            blocked.append({"index": index, "kind": action, "reason": "rewrite path is required"})
            continue
        if not isinstance(old_text, str) or old_text == "":
            blocked.append({"index": index, "kind": action, "path": path_value, "reason": "old text is required"})
            continue
        if not isinstance(new_text, str):
            blocked.append({"index": index, "kind": action, "path": path_value, "reason": "new text is required"})
            continue

        try:
            target_path = _safe_rewrite_path(root, path_value)
            current_text = target_path.read_text(encoding="utf-8")
        except Exception as exc:
            blocked.append({"index": index, "kind": action, "path": path_value, "reason": str(exc)})
            continue
        if old_text not in current_text:
            blocked.append(
                {
                    "index": index,
                    "kind": action,
                    "path": relative_path(root, target_path),
                    "reason": "old text not found",
                }
            )
            continue

        atomic_write_text(target_path, current_text.replace(old_text, new_text, 1))
        applied.append(
            {
                "index": index,
                "kind": action,
                "path": relative_path(root, target_path),
            }
        )
    return applied, blocked


def _safe_rewrite_path(root: Path, path_value: str) -> Path:
    root_path = root.resolve()
    candidate = Path(path_value)
    if not candidate.is_absolute():
        candidate = root_path / candidate
    target = candidate.resolve()
    try:
        target.relative_to(root_path)
    except ValueError as exc:
        raise ValueError("rewrite path must stay inside the repo root") from exc
    return target


def _remedy_for_stale_entry(item: dict[str, Any]) -> str:
    return (
        f"Inspect agent registry entry '{item.get('agent_id')}'. "
        "Regenerate Hermes profiles from current command output before applying."
    )


def _preview_path(root: Path, preview_id: str) -> Path:
    if not SAFE_PREVIEW_ID.fullmatch(preview_id):
        raise ValueError("preview_id must be a 32-character lowercase hex id")
    return cleanup_dir(root) / preview_id / "preview.json"


def cleanup_dir(root: Path) -> Path:
    return root / ".devflow" / "hermes-profile-cleanup"


def _read_json_object(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"missing evidence file: {path}") from exc


@hermes_profiles_app.command("validate")
def hermes_profiles_validate_command(
    json_output: bool = typer.Option(False, "--json", help="Print validation report as JSON."),
) -> None:
    """Report Hermes profile readiness, registry drift, and fallback behavior."""
    typer.echo(render_hermes_profiles_validate(Path.cwd(), json_output=json_output), nl=False)


@hermes_profiles_app.command("cleanup")
def hermes_profiles_cleanup_command(
    preview: bool = typer.Option(False, "--preview", help="Write cleanup preview evidence."),
    apply: bool = typer.Option(False, "--apply", help="Apply a previously written cleanup preview."),
    preview_id: str | None = typer.Option(None, "--preview-id", help="Preview id to apply."),
    json_output: bool = typer.Option(False, "--json", help="Print command result as JSON."),
) -> None:
    """Preview or apply Hermes profile cleanup candidates."""
    root = Path.cwd()
    if preview == apply:
        typer.echo("Specify exactly one of --preview or --apply", err=True)
        raise typer.Exit(code=1)

    if apply:
        if not preview_id:
            typer.echo("--apply requires --preview-id", err=True)
            raise typer.Exit(code=1)
        try:
            payload = build_hermes_profiles_cleanup_apply(root, preview_id=preview_id)
        except Exception as exc:
            typer.echo(f"Error: {exc}", err=True)
            raise typer.Exit(code=1) from exc
        if json_output:
            typer.echo(json.dumps(payload, indent=2, sort_keys=True), nl=False)
            return
        lines = [
            "Hermes Profile Cleanup Apply",
            f"preview_id: {payload['preview_id']}",
            f"status: {payload['status']}",
            f"manual_review_required: {payload.get('manual_review_required', False)}",
            f"apply_path: {payload['apply_path']}",
        ]
        typer.echo("\n".join(lines) + "\n", nl=False)
        return

    payload = build_hermes_profiles_cleanup_preview(root)
    if json_output:
        typer.echo(json.dumps(payload, indent=2, sort_keys=True), nl=False)
    else:
        lines = [
            "Hermes Profile Cleanup Preview",
            f"preview_id: {payload['preview_id']}",
            f"status: {payload['status']}",
            f"preview_path: {payload['preview_path']}",
            f"candidate_count: {payload['candidate_count']}",
        ]
        typer.echo("\n".join(lines) + "\n", nl=False)


__all__ = [
    "hermes_profiles_app",
    "build_hermes_profiles_validation",
    "build_hermes_profiles_cleanup_preview",
    "apply_hermes_profiles_cleanup",
]
