"""Hermes Telegram gateway handler for /df (DevFlow intent-to-goal) automation.
Plugs into the gateway stream_handler loop.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from devflow.control_room.df_telegram_bridge import run_telegram_to_devflow_pipeline


DF_COMMAND_RE = re.compile(r"^/df\s+(.+)", re.IGNORECASE)


def parse_df_command(raw_message: str) -> str | None:
    raw_message = raw_message.strip()
    match = DF_COMMAND_RE.match(raw_message)
    return match.group(1).strip() if match else None


async def handle_telegram_message(
    message_text: str,
    sender_id: int | str | None = None,
    chat_id: int | str | None = None,
    bot_token: str | None = None,
    repo_path: str | Path | None = None,
) -> tuple[bool, str, dict[str, Any]]:
    """Called from gateway stream_handler for each inbound telegram message.
    Returns (should_respond: bool, response_text: str, extra: dict).
    """
    if repo_path is None:
        repo_path = Path(__file__).resolve().parents[3]  # devflow/

    intent_text = parse_df_command(message_text)
    if not intent_text:
        return (False, "", {})

    result = run_telegram_to_devflow_pipeline(intent_text, Path(repo_path))

    if result["status"] == "error":
        response = (
            f"❌ **DevFlow Error**\n\n"
            f"Failed to process your intent: `{result['error_type']}: {result['error']}`"
        )
    else:
        goal_id = result.get("goal_id", "??")
        task_ids = result.get("task_ids", [])
        intent = result.get("intent", {})
        goal_title = intent.get("goal_title", "??")
        priority = intent.get("priority", "medium").upper()
        effort = intent.get("effort", "medium").title()
        affected = intent.get("affected_areas", [])

        response_lines = [
            f"🚀 **DevFlow Intent Received**",
            f"",
            f"Goal: **{goal_id}**",
            f"Title: *{goal_title}*",
            f"Priority: *{priority}*",
            f"Effort: *{effort}*",
            f"Affected areas: {', '.join(affected)}",
            f"",
            f"📋 **Task Slices**",
        ]

        for tid in task_ids:
            response_lines.append(f"  ↳ `{tid}` — dispatched")

        response_lines.extend([
            "",
            "📂 **Artifacts:** goal.md, prd.md, grill.md, decisions.yaml, "
            "open-questions.yaml, out-of-scope.md, context-pointers.yaml, "
            "risks.md, handoff.md, task-slices.yaml",
        ])

        response = "\n".join(response_lines)

    return (True, response, result)
