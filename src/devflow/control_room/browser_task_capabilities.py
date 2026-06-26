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


_TASK_CAPABILITY_TEMPLATES: dict[str, tuple[str, str]] = {
    "inspect": ("Inspect", "devflow task show {task_id}"),
    "inspect_log": ("Inspect log", "devflow task log {task_id}"),
    "task_packet": ("Task packet", "devflow task packet {task_id}"),
    "review_capsule": ("Review capsule", "devflow task capsule {task_id}"),
    "start_shell": ("Start shell", "devflow task run {task_id} --worker shell -- <command>"),
    "retry": ("Retry", "devflow task run {task_id} --worker shell -- <command>"),
    "verify": ("Verify", 'devflow task verify {task_id} --shell "<command>"'),
    "review_preview": ("Review preview", "devflow task promote-preview {task_id}"),
    "promote": ("Promote", "devflow task promote {task_id}"),
    "cleanup_preview": ("Cleanup preview", "devflow task cleanup {task_id} --preview"),
    "close": (
        "Close",
        'devflow task close {task_id} --outcome evidence-only --reason "<reason>"',
    ),
}


def scope_task_command(command: str, project_id: str | None) -> str:
    if not project_id or "--project" in command or not command.startswith("devflow task "):
        return command
    before_separator, separator, after_separator = command.partition(" -- ")
    scoped = f"{before_separator} --project {project_id}"
    if separator:
        return f"{scoped}{separator}{after_separator}"
    return scoped


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


def build_task_capability(
    intent: str,
    task_id: str,
    *,
    project_id: str | None = None,
    enabled: bool = True,
    command: str | None = None,
    label: str | None = None,
    scope: str = "task",
) -> BrowserTaskCapability:
    if intent == "next_safe_action":
        if not command:
            raise ValueError("next_safe_action task capability requires a command")
        capability_label = label or label_for_intent(intent)
        capability_command = command
    elif intent in _TASK_CAPABILITY_TEMPLATES:
        default_label, template = _TASK_CAPABILITY_TEMPLATES[intent]
        capability_label = label or default_label
        capability_command = command or template.format(task_id=task_id)
    else:
        raise ValueError(f"Unknown task capability intent: {intent}")

    return build_browser_task_capability(
        intent,
        capability_label,
        scope_task_command(capability_command, project_id),
        scope=scope,
        enabled=enabled,
    )


def build_task_action_capabilities(
    task_id: str,
    *,
    project_id: str | None,
    next_action_command: str | None,
    ready_to_promote: bool,
) -> tuple[BrowserTaskCapability, ...]:
    capabilities: list[BrowserTaskCapability] = []
    if _usable_command(next_action_command):
        next_action_intent = intent_for_command(str(next_action_command))
        capabilities.append(
            build_task_capability(
                next_action_intent,
                task_id,
                project_id=project_id,
                command=next_action_command,
                label="Next safe action",
            )
        )

    capabilities.extend(
        [
            build_task_capability("inspect", task_id, project_id=project_id, label="Show task"),
            build_task_capability("review_capsule", task_id, project_id=project_id),
            build_task_capability("inspect_log", task_id, project_id=project_id, label="Task log"),
            build_task_capability("task_packet", task_id, project_id=project_id),
        ]
    )
    if ready_to_promote:
        capabilities.extend(
            [
                build_task_capability("review_preview", task_id, project_id=project_id),
                build_task_capability(
                    "promote",
                    task_id,
                    project_id=project_id,
                    label="Approve promotion",
                ),
            ]
        )
    return _dedupe_capabilities_by_command(capabilities)


def build_task_control_capabilities(
    task_id: str,
    *,
    project_id: str | None,
    task_status: str,
    next_action_command: str | None,
    suggested_next_action: str | None,
    failed_verification: bool,
    worker_failed: bool,
    timed_out: bool,
    ready_to_promote: bool,
) -> tuple[BrowserTaskCapability, ...]:
    capabilities: list[BrowserTaskCapability] = [
        build_task_capability("inspect", task_id, project_id=project_id)
    ]

    if task_status == "closed":
        cleanup = None
        if _usable_command(next_action_command) and " task cleanup " in str(next_action_command):
            cleanup = next_action_command
        if (
            not cleanup
            and _usable_command(suggested_next_action)
            and str(suggested_next_action).startswith("devflow task cleanup ")
        ):
            cleanup = suggested_next_action
        if cleanup:
            capabilities.append(
                build_task_capability(
                    "cleanup_preview",
                    task_id,
                    project_id=project_id,
                    command=cleanup,
                )
            )
        return _dedupe_capabilities_by_command(capabilities)

    if task_status == "created":
        capabilities.append(build_task_capability("start_shell", task_id, project_id=project_id))
    if failed_verification:
        capabilities.append(build_task_capability("verify", task_id, project_id=project_id))
    if worker_failed or timed_out:
        capabilities.append(build_task_capability("retry", task_id, project_id=project_id))
    if ready_to_promote:
        capabilities.extend(
            [
                build_task_capability("review_preview", task_id, project_id=project_id),
                build_task_capability("promote", task_id, project_id=project_id),
            ]
        )

    if _usable_command(next_action_command):
        scoped_next_action = scope_task_command(str(next_action_command), project_id)
        if scoped_next_action not in {capability.command for capability in capabilities}:
            next_action_intent = intent_for_command(scoped_next_action)
            capabilities.insert(
                1,
                build_task_capability(
                    next_action_intent,
                    task_id,
                    project_id=project_id,
                    command=scoped_next_action,
                    label=label_for_command(scoped_next_action),
                ),
            )

    capabilities.append(build_task_capability("close", task_id, project_id=project_id))
    return _dedupe_capabilities_by_command(capabilities)


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
    if " task capsule " in value:
        return "review_capsule"
    if " task packet " in value:
        return "task_packet"
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
        "task_packet": "Task packet",
        "review_capsule": "Review capsule",
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


def _usable_command(command: str | None) -> bool:
    return bool(command and command != "none")


def _dedupe_capabilities_by_command(
    capabilities: Iterable[BrowserTaskCapability],
) -> tuple[BrowserTaskCapability, ...]:
    seen: set[str] = set()
    deduped: list[BrowserTaskCapability] = []
    for capability in capabilities:
        if capability.command in seen:
            continue
        seen.add(capability.command)
        deduped.append(capability)
    return tuple(deduped)


__all__ = [
    "BrowserTaskCapability",
    "build_browser_task_capability",
    "build_task_action_capabilities",
    "build_task_capability",
    "build_task_control_capabilities",
    "dedupe_browser_task_capabilities",
    "intent_for_command",
    "label_for_command",
    "label_for_intent",
    "required_inputs_for_capability",
    "scope_task_command",
]
