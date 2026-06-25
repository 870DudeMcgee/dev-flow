from __future__ import annotations

from devflow.control_room.browser_task_capabilities import (
    build_browser_task_capability,
    dedupe_browser_task_capabilities,
    intent_for_command,
    label_for_intent,
    required_inputs_for_capability,
)


def test_capability_infers_intent_label_inputs_and_supervisor_policy() -> None:
    capability = build_browser_task_capability(
        "start_shell",
        "Start shell",
        "devflow task run task-0001 --worker shell -- <command>",
    )

    assert capability.intent == "start_shell"
    assert capability.label == "Start shell"
    assert capability.scope == "task"
    assert capability.enabled is True
    assert capability.required_inputs == ["shell_command"]
    assert capability.safety_class == "approval_required_worker_runtime"
    assert capability.requires_human_approval is True
    assert capability.supervisor_may_auto_run is False
    assert capability.reason


def test_command_helpers_cover_browser_task_actions() -> None:
    assert intent_for_command("devflow task verify task-0001 --shell \"<command>\"") == "verify"
    assert intent_for_command("devflow task promote-preview task-0001") == "review_preview"
    assert intent_for_command("devflow task promote task-0001") == "promote"
    assert intent_for_command("devflow task cleanup task-0001 --preview") == "cleanup_preview"
    assert intent_for_command(
        "devflow task close task-0001 --outcome evidence-only --reason \"<reason>\""
    ) == "close"
    assert intent_for_command("devflow task show task-0001") == "inspect"
    assert intent_for_command("devflow task log task-0001") == "inspect_log"
    assert label_for_intent("cleanup_preview") == "Cleanup preview"
    assert required_inputs_for_capability(
        "verify",
        "devflow task verify task-0001 --shell \"<command>\"",
    ) == ["verification_command"]
    assert required_inputs_for_capability(
        "close",
        "devflow task close task-0001 --outcome evidence-only --reason \"<reason>\"",
    ) == ["close_outcome", "close_reason"]


def test_capability_dedupe_preserves_first_capability_order() -> None:
    first = build_browser_task_capability("inspect", "Inspect", "devflow task show task-0001")
    duplicate = build_browser_task_capability("inspect", "Show task", "devflow task show task-0001")
    shell = build_browser_task_capability(
        "start_shell",
        "Start shell",
        "devflow task run task-0001 --worker shell -- <command>",
    )

    assert dedupe_browser_task_capabilities([first, duplicate, shell]) == (first, shell)
