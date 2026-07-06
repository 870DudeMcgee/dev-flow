from __future__ import annotations

import pytest

from devflow.control_room.browser_action_policy import (
    ACTION_APPROVAL_PHRASE,
    _approved_idea_classify_command_args,
    _approved_idea_evidence_command_args,
    resolve_browser_action_command,
)


def test_browser_action_policy_resolves_exact_approval_payload() -> None:
    command = 'devflow task create --definition-of-done "Done means visible evidence." "browser task"'
    classification = {
        "safety_class": "approval_required_task_state",
        "requires_human_approval": True,
    }
    payload = {
        "command": command,
        "human_approved": True,
        "approval_phrase": ACTION_APPROVAL_PHRASE,
        "approved_command": command,
    }

    resolved = resolve_browser_action_command(payload, command, classification)

    assert resolved is not None
    assert resolved.args[-5:] == ["task", "create", "--definition-of-done", "Done means visible evidence.", "browser task"]
    assert resolved.writes_promotion_context is False
    mismatched_payload = dict(payload, approved_command="devflow task list")
    assert resolve_browser_action_command(mismatched_payload, command, classification) is None


def test_approved_idea_evidence_command_args_accepts_only_safe_concrete_commands() -> None:
    accepted = [
        (
            'devflow idea park I-0001 --reason "not this week"',
            ["idea", "park", "I-0001", "--reason", "not this week"],
        ),
        (
            'devflow idea archive I-0001 --reason "duplicate"',
            ["idea", "archive", "I-0001", "--reason", "duplicate"],
        ),
    ]
    for command, expected_tail in accepted:
        args = _approved_idea_evidence_command_args(command)

        assert args[-5:] == expected_tail

    rejected = [
        "devflow idea park I-0001",
        "devflow idea park I-0001 --reason",
        "devflow idea park I-0001 --reason <reason>",
        'devflow idea park I-0001 --reason ""',
        'devflow idea park I-0001 --reason "not this week" --tag later',
        'devflow idea archive I-0001 --reason "duplicate" extra',
        "devflow idea classify I-0001 --maturity candidate --note <note>",
        "devflow idea promote I-0001 --to task --rationale <rationale>",
    ]
    for command in rejected:
        with pytest.raises(ValueError):
            _approved_idea_evidence_command_args(command)


def test_approved_idea_classify_command_args_accepts_only_safe_concrete_commands() -> None:
    accepted = [
        (
            'devflow idea classify I-0001 --maturity candidate --note "ready for planning"',
            ["idea", "classify", "I-0001", "--maturity", "candidate", "--note", "ready for planning"],
        ),
        (
            'devflow idea classify I-0001 --maturity goal_ready --note "scoped" --tag launchpad',
            ["idea", "classify", "I-0001", "--maturity", "goal_ready", "--note", "scoped", "--tag", "launchpad"],
        ),
    ]
    for command, expected_tail in accepted:
        args = _approved_idea_classify_command_args(command)

        assert args[-len(expected_tail) :] == expected_tail

    rejected = [
        "devflow idea classify I-0001",
        "devflow idea classify 0001 --maturity candidate --note ready",
        "devflow idea classify I-0001 --maturity nope --note ready",
        "devflow idea classify I-0001 --maturity candidate",
        "devflow idea classify I-0001 --maturity candidate --note",
        "devflow idea classify I-0001 --maturity candidate --note <note>",
        'devflow idea classify I-0001 --maturity candidate --note ""',
        'devflow idea classify I-0001 --maturity candidate --note "ready" extra',
        'devflow idea classify I-0001 --maturity candidate --note "ready" --shell echo',
        "devflow idea promote I-0001 --to task --rationale ready",
    ]
    for command in rejected:
        with pytest.raises(ValueError):
            _approved_idea_classify_command_args(command)
