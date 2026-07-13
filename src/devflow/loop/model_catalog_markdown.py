"""Render the shared model catalog into a generated Obsidian section."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping


START_MARKER = "<!-- DEVFLOW-MODEL-CATALOG:START -->"
END_MARKER = "<!-- DEVFLOW-MODEL-CATALOG:END -->"


def _escape_cell(value: object) -> str:
    return str(value or "").replace("|", "\\|").replace("\n", " ").strip()


def _integer(value: object) -> int:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return 0


def _number(value: object) -> str:
    try:
        number = float(str(value))
    except (TypeError, ValueError):
        return "0"
    return str(int(number)) if number.is_integer() else f"{number:.2f}".rstrip("0").rstrip(".")


def _capability_labels(model: Mapping[str, object]) -> str:
    capabilities = model.get("capabilities")
    if not isinstance(capabilities, Mapping):
        return "—"
    labels = [
        name.replace("_", " ")
        for name, enabled in capabilities.items()
        if enabled is True
    ]
    return ", ".join(sorted(labels)) or "—"


def render_model_catalog_markdown(catalog: Mapping[str, object], snapshot: Mapping[str, object]) -> str:
    """Render current inventory and rankings without operator write controls."""

    lines = [
        "## DevFlow Worker Model Catalog",
        "",
        "> Generated read-only inventory. DevFlow remains the active routing and health-control surface.",
        "",
        f"Last checked: {_escape_cell(catalog.get('fetched_at')) or 'not yet refreshed'}",
        "",
        f"Free text-chat models: **{_integer(snapshot.get('model_count'))}**",
        "",
    ]

    counts = snapshot.get("capability_counts")
    if isinstance(counts, Mapping):
        lines.extend([
            "| Capability | Models |",
            "|---|---:|",
        ])
        for name in ("tool_calling", "reasoning", "coding", "image_input", "structured_output"):
            lines.append(f"| {_escape_cell(name.replace('_', ' ').title())} | {_integer(counts.get(name))} |")
        lines.append("")

    lines.extend([
        "### Free-Cloud Role Rankings",
        "",
        "Only the three highest-ranked routine candidates are shown for each worker profile.",
        "",
        "| Profile | Rank | Model | Quality | Confidence | Samples | Reliability | Speed |",
        "|---|---:|---|---:|---|---:|---:|---:|",
    ])
    profiles = snapshot.get("profiles")
    if isinstance(profiles, Mapping):
        for profile, candidates in profiles.items():
            if not isinstance(candidates, list):
                continue
            for rank, candidate in enumerate(candidates, start=1):
                if not isinstance(candidate, Mapping):
                    continue
                speed = candidate.get("speed_score")
                speed_text = f"{speed} tok/s" if speed is not None else "not measured"
                lines.append(
                    "| "
                    + " | ".join([
                        _escape_cell(profile),
                        str(rank),
                        _escape_cell(candidate.get("model_id")),
                        f"{_number(candidate.get('quality_score'))}/100",
                        _escape_cell(candidate.get("confidence")),
                        str(_integer(candidate.get("sample_count"))),
                        f"{_number(candidate.get('reliability_score'))}/100",
                        _escape_cell(speed_text),
                    ])
                    + " |"
                )
    lines.append("")

    quarantined = snapshot.get("quarantined_roles")
    lines.extend(["### Human Review Holds", ""])
    if isinstance(quarantined, list) and quarantined:
        lines.extend(["| Model | Profile | Reason |", "|---|---|---|"])
        for entry in quarantined:
            if isinstance(entry, Mapping):
                lines.append(
                    f"| {_escape_cell(entry.get('model_id'))} | "
                    f"{_escape_cell(entry.get('profile'))} | "
                    f"{_escape_cell(entry.get('reason'))} |"
                )
    else:
        lines.append("No model-role pairs are awaiting human review.")
    lines.append("")

    lines.extend([
        "### Free-Cloud Inventory",
        "",
        "| Model | Capabilities | Eligible profiles | Context | First seen | Last seen |",
        "|---|---|---|---:|---|---|",
    ])
    models = catalog.get("models")
    if isinstance(models, list):
        for model in models:
            if not isinstance(model, Mapping):
                continue
            profiles_value = model.get("eligible_profiles")
            profile_text = ", ".join(str(value) for value in profiles_value) if isinstance(profiles_value, list) else "—"
            lines.append(
                "| "
                + " | ".join([
                    _escape_cell(model.get("id")),
                    _escape_cell(_capability_labels(model)),
                    _escape_cell(profile_text),
                    str(_integer(model.get("context_length"))),
                    _escape_cell(model.get("first_seen")),
                    _escape_cell(model.get("last_seen")),
                ])
                + " |"
            )
    return "\n".join(lines).rstrip() + "\n"


def update_model_dashboard(path: Path | str, generated_markdown: str) -> bool:
    """Replace only the marked generated block and preserve all human notes."""

    dashboard = Path(path)
    existing = dashboard.read_text(encoding="utf-8") if dashboard.exists() else ""
    block = f"{START_MARKER}\n{generated_markdown.rstrip()}\n{END_MARKER}"
    if START_MARKER in existing and END_MARKER in existing:
        prefix, remainder = existing.split(START_MARKER, 1)
        _, suffix = remainder.split(END_MARKER, 1)
        updated = f"{prefix}{block}{suffix}"
    else:
        separator = "" if not existing else ("\n" if existing.endswith("\n") else "\n\n")
        updated = f"{existing}{separator}{block}\n"
    if updated == existing:
        return False
    dashboard.parent.mkdir(parents=True, exist_ok=True)
    dashboard.write_text(updated, encoding="utf-8")
    return True


__all__ = [
    "END_MARKER",
    "START_MARKER",
    "render_model_catalog_markdown",
    "update_model_dashboard",
]
