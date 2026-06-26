from __future__ import annotations

from devflow.control_room.browser_task_capabilities import (
    build_task_action_capabilities,
    build_task_capability,
    build_task_control_capabilities,
    build_browser_task_capability,
    dedupe_browser_task_capabilities,
    intent_for_command,
    label_for_intent,
    required_inputs_for_capability,
    scope_task_command,
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


def test_scope_task_command_adds_project_only_to_task_commands() -> None:
    assert (
        scope_task_command("devflow task show task-0001", "demo")
        == "devflow task show task-0001 --project demo"
    )
    assert (
        scope_task_command("devflow task run task-0001 --worker shell -- <command>", "demo")
        == "devflow task run task-0001 --worker shell --project demo -- <command>"
    )
    assert (
        scope_task_command('devflow task verify task-0001 --shell "<command>"', "demo")
        == 'devflow task verify task-0001 --shell "<command>" --project demo'
    )
    assert (
        scope_task_command("devflow project status demo", "demo")
        == "devflow project status demo"
    )


def test_build_task_capability_owns_canonical_task_commands() -> None:
    expected = {
        "inspect": ("Inspect", "devflow task show task-0001 --project demo", []),
        "inspect_log": ("Inspect log", "devflow task log task-0001 --project demo", []),
        "task_packet": ("Task packet", "devflow task packet task-0001 --project demo", []),
        "review_capsule": (
            "Review capsule",
            "devflow task capsule task-0001 --project demo",
            [],
        ),
        "start_shell": (
            "Start shell",
            "devflow task run task-0001 --worker shell --project demo -- <command>",
            ["shell_command"],
        ),
        "retry": (
            "Retry",
            "devflow task run task-0001 --worker shell --project demo -- <command>",
            ["shell_command"],
        ),
        "verify": (
            "Verify",
            'devflow task verify task-0001 --shell "<command>" --project demo',
            ["verification_command"],
        ),
        "review_preview": (
            "Review preview",
            "devflow task promote-preview task-0001 --project demo",
            [],
        ),
        "promote": ("Promote", "devflow task promote task-0001 --project demo", []),
        "cleanup_preview": (
            "Cleanup preview",
            "devflow task cleanup task-0001 --preview --project demo",
            [],
        ),
        "close": (
            "Close",
            (
                'devflow task close task-0001 --outcome evidence-only '
                '--reason "<reason>" --project demo'
            ),
            ["close_outcome", "close_reason"],
        ),
    }

    for intent, (label, command, required_inputs) in expected.items():
        capability = build_task_capability(intent, "task-0001", project_id="demo")
        assert capability.intent == intent
        assert capability.label == label
        assert capability.command == command
        assert capability.required_inputs == required_inputs

    start_shell = build_task_capability("start_shell", "task-0001")
    assert start_shell.safety_class == "approval_required_worker_runtime"
    assert start_shell.requires_human_approval is True
    assert start_shell.supervisor_may_auto_run is False

    verify = build_task_capability("verify", "task-0001")
    assert verify.safety_class == "approval_required_worker_runtime"
    assert verify.requires_human_approval is True
    assert verify.supervisor_may_auto_run is False

    promote = build_task_capability("promote", "task-0001")
    assert promote.safety_class == "approval_required_git"
    assert promote.requires_human_approval is True
    assert promote.supervisor_may_auto_run is False

    close = build_task_capability("close", "task-0001")
    assert close.safety_class == "approval_required_task_state"
    assert close.requires_human_approval is True
    assert close.supervisor_may_auto_run is False


def test_build_task_capability_rejects_unknown_intents() -> None:
    try:
        build_task_capability("invented", "task-0001")
    except ValueError as exc:
        assert "Unknown task capability intent" in str(exc)
    else:
        raise AssertionError("build_task_capability should reject unknown intents")


def test_build_task_action_capabilities_orders_current_task_actions() -> None:
    capabilities = build_task_action_capabilities(
        "task-0001",
        project_id="demo",
        next_action_command='devflow task verify task-0001 --shell "<command>" --project demo',
        ready_to_promote=True,
    )

    assert [capability.label for capability in capabilities] == [
        "Next safe action",
        "Show task",
        "Review capsule",
        "Task log",
        "Task packet",
        "Review preview",
        "Approve promotion",
    ]
    assert [capability.intent for capability in capabilities] == [
        "verify",
        "inspect",
        "review_capsule",
        "inspect_log",
        "task_packet",
        "review_preview",
        "promote",
    ]
    assert capabilities[0].command == (
        'devflow task verify task-0001 --shell "<command>" --project demo'
    )
    assert capabilities[-1].command == "devflow task promote task-0001 --project demo"


def test_build_task_control_capabilities_follow_task_state() -> None:
    created = build_task_control_capabilities(
        "task-0001",
        project_id=None,
        task_status="created",
        next_action_command="devflow task run task-0001 --worker shell -- <command>",
        suggested_next_action="devflow task run task-0001 --worker shell -- <command>",
        failed_verification=False,
        worker_failed=False,
        timed_out=False,
        ready_to_promote=False,
    )
    assert [capability.intent for capability in created] == ["inspect", "start_shell", "close"]

    failed_verification = build_task_control_capabilities(
        "task-0002",
        project_id=None,
        task_status="failed",
        next_action_command='devflow task verify task-0002 --shell "<command>"',
        suggested_next_action='devflow task verify task-0002 --shell "<command>"',
        failed_verification=True,
        worker_failed=False,
        timed_out=False,
        ready_to_promote=False,
    )
    assert [capability.intent for capability in failed_verification] == [
        "inspect",
        "verify",
        "close",
    ]

    worker_failed = build_task_control_capabilities(
        "task-0003",
        project_id=None,
        task_status="failed",
        next_action_command="devflow task run task-0003 --worker shell -- <command>",
        suggested_next_action="devflow task run task-0003 --worker shell -- <command>",
        failed_verification=False,
        worker_failed=True,
        timed_out=True,
        ready_to_promote=False,
    )
    assert [capability.intent for capability in worker_failed] == ["inspect", "retry", "close"]

    ready_to_promote = build_task_control_capabilities(
        "task-0004",
        project_id=None,
        task_status="verified",
        next_action_command="devflow task promote-preview task-0004",
        suggested_next_action="devflow task promote-preview task-0004",
        failed_verification=False,
        worker_failed=False,
        timed_out=False,
        ready_to_promote=True,
    )
    assert [capability.intent for capability in ready_to_promote] == [
        "inspect",
        "review_preview",
        "promote",
        "close",
    ]

    closed = build_task_control_capabilities(
        "task-0005",
        project_id=None,
        task_status="closed",
        next_action_command="devflow task cleanup task-0005 --preview",
        suggested_next_action="devflow task cleanup task-0005 --preview",
        failed_verification=False,
        worker_failed=False,
        timed_out=False,
        ready_to_promote=False,
    )
    assert [capability.intent for capability in closed] == ["inspect", "cleanup_preview"]
