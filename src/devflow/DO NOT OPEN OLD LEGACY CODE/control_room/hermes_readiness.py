from __future__ import annotations

import json
import platform
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

from devflow.legacy.control_room.persistence import utc_now


SCHEMA_VERSION = 1

MESSAGES_APP_CANDIDATES = [
    Path("/System/Applications/Messages.app"),
    Path("/Applications/Messages.app"),
]
BLUEBUBBLES_CANDIDATES = [
    Path("/Applications/BlueBubbles.app"),
    Path("~/Library/Application Support/bluebubbles-server"),
    Path("~/.bluebubbles"),
]
HERMES_CONFIG_CANDIDATES = [
    Path("~/.hermes"),
    Path("~/.config/hermes"),
    Path("~/.hermes/config.yaml"),
    Path("~/.config/hermes/config.yaml"),
]


def build_hermes_imessage_readiness(
    repo_root: Path,
    *,
    home: Path | None = None,
    system_name: str | None = None,
    which: Callable[[str], str | None] = shutil.which,
) -> dict[str, Any]:
    """Return a read-only readiness projection for Hermes iMessage experiments."""

    home = home or Path.home()
    system_name = system_name or platform.system()
    is_macos = system_name == "Darwin"
    messages_app_paths = _existing_paths(MESSAGES_APP_CANDIDATES, home=home)
    bluebubbles_paths = _existing_paths(BLUEBUBBLES_CANDIDATES, home=home)
    hermes_paths = _existing_paths(HERMES_CONFIG_CANDIDATES, home=home)
    imsg_path = which("imsg")
    bluebubbles_cli = which("bluebubbles") or which("bbctl")

    checks = [
        _check("macos", "macOS platform", is_macos, system_name),
        _check(
            "messages_app",
            "Messages.app present",
            bool(messages_app_paths),
            _join_paths(messages_app_paths) or "not found in standard locations",
        ),
        _check(
            "bluebubbles",
            "BlueBubbles detectable",
            bool(bluebubbles_paths or bluebubbles_cli),
            _join_paths(bluebubbles_paths) or bluebubbles_cli or "no app/config/CLI detected",
        ),
        _check("imsg_cli", "imsg CLI detectable", bool(imsg_path), imsg_path or "not on PATH"),
        _check(
            "hermes_config",
            "Hermes config detectable",
            bool(hermes_paths),
            _join_paths(hermes_paths) or "no standard Hermes config path detected",
        ),
    ]
    ready_for_experiment = is_macos and bool(messages_app_paths) and bool(bluebubbles_paths or bluebubbles_cli or imsg_path)

    return {
        "schema_version": SCHEMA_VERSION,
        "integration": "hermes-imessage",
        "repo_root": str(repo_root.resolve()),
        "generated_at": utc_now().isoformat(),
        "readiness": "manual_experiment_possible" if ready_for_experiment else "manual_setup_required",
        "checks": checks,
        "privacy_boundary": {
            "reads_message_contents": False,
            "sends_messages": False,
            "never_reads": ["chat.db", "Messages chat.db", "iMessage transcripts", "SMS transcripts"],
            "never_sends": ["test messages", "approval prompts", "automation replies"],
            "notes": [
                "This check only inspects platform, app/config path presence, and CLI availability.",
                "It does not request Full Disk Access, Accessibility, chat database access, or network credentials.",
            ],
        },
        "permissions_not_automatically_verifiable": [
            "Messages.app signed in to the intended Apple ID",
            "BlueBubbles server installed, paired, authenticated, and network reachable",
            "Full Disk Access grants needed by BlueBubbles or imsg workflows",
            "Accessibility or Automation permissions needed by any macOS Messages skill",
            "Hermes gateway routing and profile isolation",
        ],
        "recommended_first_experiment": (
            "Wire Hermes to read-only Dev-Flow status commands and return short status replies before any send path."
        ),
        "safe_example_interactions": [
            "Dev-Flow status",
            "What needs review?",
            "What is the next safe action?",
            "Prepare a Codex prompt",
            "Summarize blocked tasks",
        ],
        "forbidden_example_interactions": [
            "Push it",
            "Merge everything",
            "Delete old worktrees",
            "Let agents fix whatever they want",
        ],
        "next_manual_steps": [
            "Choose BlueBubbles or imsg as the first integration path.",
            "Keep the first Hermes profile read-only and scoped to supervisor-safe Dev-Flow commands.",
            "Review permission prompts manually; do not grant broad access just for this readiness check.",
            "Use explicit approval text before any future mutation command.",
        ],
    }


def render_hermes_imessage_check(root: Path, *, json_output: bool) -> str:
    payload = build_hermes_imessage_readiness(root)
    if json_output:
        return json.dumps(payload, sort_keys=True, indent=2) + "\n"

    lines = [
        "Hermes iMessage Readiness",
        f"readiness: {payload['readiness']}",
        f"repo_root: {payload['repo_root']}",
        "",
        "Checks",
    ]
    for check in payload["checks"]:
        lines.append(f"- {check['id']}: {check['status']} ({check['detail']})")
    lines.extend(
        [
            "",
            "Privacy boundary",
            "- does not read message contents",
            "- does not send messages",
            "- does not inspect chat.db",
            "",
            f"Recommended first experiment: {payload['recommended_first_experiment']}",
        ]
    )
    return "\n".join(lines) + "\n"


def _existing_paths(candidates: list[Path], *, home: Path) -> list[str]:
    found: list[str] = []
    for candidate in candidates:
        expanded = _expand_home(candidate, home=home)
        if expanded.exists():
            found.append(str(expanded))
    return found


def _expand_home(path: Path, *, home: Path) -> Path:
    raw = str(path)
    if raw == "~":
        return home
    if raw.startswith("~/"):
        return home / raw[2:]
    return path


def _check(check_id: str, label: str, ok: bool, detail: str) -> dict[str, str]:
    return {
        "id": check_id,
        "label": label,
        "status": "present" if ok else "missing",
        "detail": detail,
    }


def _join_paths(paths: list[str]) -> str:
    return ", ".join(paths)
