from __future__ import annotations

from collections.abc import Iterable

from pydantic import BaseModel, Field

from devflow.control_room.supervisor_surface import classify_supervisor_command


class BrowserTaskCapability(BaseModel):
    intent: str
    label: str
    command: str
    scope: str = "task"
    enabled: bool = True
    safety_class: str
    requires_human_approval: bool
    supervisor_may_auto_run: bool
    required_inputs: list[str] = Field(default_factory=list)
    reason: str | None = None


def build_browser_task_capability(
    intent: str,
    label: str,
    command: str,
    *,
    scope: str = "task",
    enabled: bool = True,
) -> BrowserTaskCapability:
    classification = classify_supervisor_command(command)
    return BrowserTaskCapability(
        intent=intent,
        label=label,
        command=command,
        scope=scope,
        enabled=enabled,
        safety_class=str(classification["safety_class"]),
        requires_human_approval=bool(classification["requires_human_approval"]),
        supervisor_may_auto_run=bool(classification["supervisor_may_auto_run"]),
        required_inputs=required_inputs_for_capability(intent, command),
        reason=classification.get("why_not_auto_runnable"),
    )


def intent_for_command(command: str) -> str:
    value = str(command or "")
    if " task run " in value and "--worker shell" in value:
        return "start_shell"
    if " task verify " in value:
        return "verify"
    if " task promote-preview " in value:
        return "review_preview"
    if " task promote " in value:
        return "promote"
    if " task cleanup " in value and "--preview" in value:
        return "cleanup_preview"
    if " task close " in value:
        return "close"
    if " task log " in value:
        return "inspect_log"
    if " task show " in value:
        return "inspect"
    return "next_safe_action"


def label_for_intent(intent: str) -> str:
    labels = {
        "start_shell": "Start shell",
        "retry": "Retry",
        "verify": "Verify",
        "review_preview": "Review preview",
        "promote": "Promote",
        "cleanup_preview": "Cleanup preview",
        "close": "Close",
        "inspect": "Inspect",
        "inspect_log": "Inspect log",
        "next_safe_action": "Next safe action",
    }
    fallback = " ".join(part.capitalize() for part in intent.split("_")) or "Next safe action"
    return labels.get(intent, fallback)


def label_for_command(command: str) -> str:
    return label_for_intent(intent_for_command(command))


def required_inputs_for_capability(intent: str, command: str) -> list[str]:
    value = str(command or "")
    if intent in {"start_shell", "retry"} or value.endswith(" -- <command>"):
        return ["shell_command"]
    if intent == "verify" or ' --shell "<command>"' in value or " --shell '<command>'" in value:
        return ["verification_command"]
    if intent == "close" or "<reason>" in value:
        return ["close_outcome", "close_reason"]
    return []


def dedupe_browser_task_capabilities(
    capabilities: Iterable[BrowserTaskCapability],
) -> tuple[BrowserTaskCapability, ...]:
    seen: set[tuple[str, str]] = set()
    deduped: list[BrowserTaskCapability] = []
    for capability in capabilities:
        key = (capability.intent, capability.command)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(capability)
    return tuple(deduped)


__all__ = [
    "BrowserTaskCapability",
    "build_browser_task_capability",
    "dedupe_browser_task_capabilities",
    "intent_for_command",
    "label_for_command",
    "label_for_intent",
    "required_inputs_for_capability",
]
