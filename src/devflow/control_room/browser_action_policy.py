"""Canonical browser action policy projection and exact approval gate.

This module is intentionally declarative. It owns the browser-visible
allowed/blocked mutation labels shared by the supervisor policy, task workbench,
and operating-layer snapshots. It does not execute commands or loosen the
server's exact approval parsers.
"""

from __future__ import annotations

import re
import shlex
import sys
from dataclasses import dataclass
from typing import Callable


ACTION_APPROVAL_PHRASE = "I approve this exact Dev-Flow command"
PURE_READ_ONLY = "pure_read_only"
APPROVAL_REQUIRED_EVIDENCE_WRITING = "approval_required_evidence_writing"
APPROVAL_REQUIRED_TASK_STATE = "approval_required_task_state"
APPROVAL_REQUIRED_WORKER_RUNTIME = "approval_required_worker_runtime"
APPROVAL_REQUIRED_GIT = "approval_required_git"

BROWSER_ALLOWED_MUTATIONS: tuple[str, ...] = (
    "idea capture",
    "task creation",
    "shell worker execution",
    "serial local-agent packet creation",
    "model/provider onboarding",
    "task verification",
    "task promotion",
    "architecture evidence refresh",
)

BROWSER_BLOCKED_MUTATIONS: tuple[str, ...] = (
    "non-shell worker execution",
    "local/provider model execution",
    "Hermes worker runtime launch",
    "patch application",
    "cleanup apply",
    "sync",
    "push",
    "project publication",
    "autonomous routing",
    "broad mutation",
)


@dataclass(frozen=True)
class BrowserActionCommand:
    args: list[str]
    writes_promotion_context: bool = False


@dataclass(frozen=True)
class _BrowserActionRule:
    safety_class: str
    command_args: Callable[[str], list[str]]
    writes_promotion_context: bool = False


def get_browser_allowed_mutations() -> list[str]:
    """Return browser mutations that are allowed with exact approval gates."""
    return list(BROWSER_ALLOWED_MUTATIONS)


def get_browser_blocked_mutations() -> list[str]:
    """Return browser mutations that remain blocked from browser execution."""
    return list(BROWSER_BLOCKED_MUTATIONS)


def resolve_browser_action_command(
    payload: dict[str, object],
    command: str,
    classification: dict[str, object],
) -> BrowserActionCommand | None:
    """Return runnable args only when the command matches a browser-approved gate."""

    safety_class = classification.get("safety_class")
    if safety_class == PURE_READ_ONLY:
        return BrowserActionCommand(args=_supervisor_read_only_command_args(command))

    for rule in _BROWSER_ACTION_RULES:
        if safety_class != rule.safety_class:
            continue
        try:
            args = rule.command_args(command)
        except ValueError:
            continue
        if _approval_payload_matches(payload, command):
            return BrowserActionCommand(
                args=args,
                writes_promotion_context=rule.writes_promotion_context,
            )
    return None


def promotion_task_id_from_command(command: str) -> str:
    _approved_task_promotion_command_args(command)
    normalized = _normalize_devflow_command_tokens(shlex.split(command))
    if len(normalized) < 4:
        raise ValueError("task promotion command requires a task id")
    return normalized[3]


def _supervisor_read_only_command_args(command: str) -> list[str]:
    tokens = shlex.split(command)
    return _devflow_command_args_from_tokens(tokens)


def _approved_idea_capture_command_args(command: str) -> list[str]:
    tokens = shlex.split(command)
    normalized = _normalize_devflow_command_tokens(tokens)
    if len(normalized) < 4 or normalized[1:3] != ["idea", "capture"]:
        raise ValueError("only approved idea capture may run from the operating layer")
    allowed_value_options = {"--title", "--source", "--tag"}
    index = 3
    idea_texts: list[str] = []
    while index < len(normalized):
        token = normalized[index]
        if token in allowed_value_options:
            if index + 1 >= len(normalized) or normalized[index + 1].startswith("-"):
                raise ValueError(f"approved browser idea capture requires a value after {token}")
            if token == "--title" and _is_placeholder_text(normalized[index + 1], field="title"):
                raise ValueError("approved browser idea capture requires a concrete title when --title is used")
            index += 2
            continue
        if token.startswith("-"):
            raise ValueError("approved browser idea capture allows only --title, --source, and --tag")
        idea_texts.append(token)
        index += 1
    if len(idea_texts) != 1:
        raise ValueError("approved browser idea capture requires one quoted idea body")
    if _is_placeholder_text(idea_texts[0], field="idea"):
        raise ValueError("approved browser idea capture requires concrete brainstorm text")
    return _devflow_command_args_from_tokens(tokens)


def _approved_idea_evidence_command_args(command: str) -> list[str]:
    tokens = shlex.split(command)
    normalized = _normalize_devflow_command_tokens(tokens)
    if len(normalized) != 6 or normalized[1] != "idea" or normalized[2] not in {"park", "archive"}:
        raise ValueError("only approved idea park/archive may run from the operating layer")
    idea_id = normalized[3]
    if not idea_id or idea_id.startswith("-"):
        raise ValueError("approved idea park/archive requires an idea id")
    if normalized[4] != "--reason":
        raise ValueError("approved idea park/archive requires exactly --reason")
    reason = normalized[5]
    if _is_placeholder_text(reason, field="reason") or len(reason.strip()) < 3:
        raise ValueError("approved idea park/archive requires a concrete reason")
    return _devflow_command_args_from_tokens(tokens)


def _approved_idea_classify_command_args(command: str) -> list[str]:
    tokens = shlex.split(command)
    normalized = _normalize_devflow_command_tokens(tokens)
    if len(normalized) < 6 or normalized[1] != "idea" or normalized[2] != "classify":
        raise ValueError("only approved idea classify may run from the operating layer")
    idea_id = normalized[3]
    if not idea_id or not re.fullmatch(r"I-\d{4}", idea_id):
        raise ValueError("approved idea classify requires a valid idea id (I-0000)")
    values = _parse_exact_options(
        normalized[4:],
        value_options={"--maturity", "--note", "--tag"},
        flags=set(),
        command_label="approved idea classify",
    )
    maturity_value = values.get("--maturity", "")
    allowed_maturities = {"spark", "concept", "candidate", "goal_ready", "task_ready"}
    if maturity_value not in allowed_maturities:
        raise ValueError(f"approved idea classify requires one of: {', '.join(sorted(allowed_maturities))}")
    note_value = values.get("--note", "")
    if _is_placeholder_text(note_value, field="note") or len(note_value.strip()) < 1:
        raise ValueError("approved idea classify requires a concrete (non-empty, non-placeholder) note")
    return _devflow_command_args_from_tokens(tokens)


def _approved_architecture_refresh_command_args(command: str) -> list[str]:
    tokens = shlex.split(command)
    normalized = _normalize_devflow_command_tokens(tokens)
    # Accept ONLY the exact approved Graphify refresh command — both flags, no
    # extras, in any order. This intentionally rejects bare audit, --json,
    # arbitrary options, or positional values.
    if normalized[:3] != ["devflow", "architecture", "audit"]:
        raise ValueError("only the approved architecture evidence refresh may run from the operating layer")
    flags = normalized[3:]
    if sorted(flags) != ["--install-graphify", "--write-doc"]:
        raise ValueError(
            "approved architecture evidence refresh must be exactly "
            "'devflow architecture audit --install-graphify --write-doc'"
        )
    return _devflow_command_args_from_tokens(tokens)


def _approved_task_creation_command_args(command: str) -> list[str]:
    tokens = shlex.split(command)
    normalized = _normalize_devflow_command_tokens(tokens)
    if len(normalized) < 4 or normalized[1:3] != ["task", "create"]:
        raise ValueError("only approved task creation may run from the operating layer")
    allowed_flags = {"--git-worktree"}
    allowed_value_options = {"--project", "--definition-of-done"}
    index = 3
    titles: list[str] = []
    while index < len(normalized):
        token = normalized[index]
        if token in allowed_flags:
            index += 1
            continue
        if token in allowed_value_options:
            if index + 1 >= len(normalized) or normalized[index + 1].startswith("-"):
                if token == "--project":
                    raise ValueError("approved browser task creation requires a project id after --project")
                raise ValueError("approved browser task creation requires definition text after --definition-of-done")
            if token == "--definition-of-done" and _is_placeholder_text(normalized[index + 1], field="definition-of-done"):
                raise ValueError("approved browser task creation requires concrete definition-of-done text")
            index += 2
            continue
        if token.startswith("-"):
            raise ValueError("approved browser task creation allows only --project, --git-worktree, and --definition-of-done")
        titles.append(token)
        index += 1
    if len(titles) != 1:
        raise ValueError("approved browser task creation requires one quoted task title")
    if _is_placeholder_text(titles[0], field="title"):
        raise ValueError("approved browser task creation requires a concrete task title")
    return _devflow_command_args_from_tokens(tokens)


def _approved_task_close_command_args(command: str) -> list[str]:
    tokens = shlex.split(command)
    normalized = _normalize_devflow_command_tokens(tokens)
    if len(normalized) < 4 or normalized[1:3] != ["task", "close"]:
        raise ValueError("only approved task close may run from the operating layer")
    task_id = normalized[3]
    if not task_id or task_id.startswith("-"):
        raise ValueError("task close command requires a task id")
    values = _parse_exact_options(
        normalized[4:],
        value_options={"--outcome", "--reason"},
        flags=set(),
        command_label="approved task close",
    )
    for option, field in (("--outcome", "outcome"), ("--reason", "reason")):
        value = values.get(option, "")
        if _is_placeholder_text(value, field=field) or len(value.strip()) < 3:
            raise ValueError(f"approved task close requires a concrete {field}")
    return _devflow_command_args_from_tokens(tokens)


def _approved_cleanup_preview_command_args(command: str) -> list[str]:
    tokens = shlex.split(command)
    normalized = _normalize_devflow_command_tokens(tokens)
    if len(normalized) != 5 or normalized[1:3] != ["task", "cleanup"]:
        raise ValueError("only approved cleanup preview may run from the operating layer")
    task_id = normalized[3]
    if not task_id or task_id.startswith("-"):
        raise ValueError("cleanup preview command requires a task id")
    if normalized[4] != "--preview":
        raise ValueError("browser cleanup is limited to --preview")
    return _devflow_command_args_from_tokens(tokens)


def _approved_shell_worker_run_command_args(command: str) -> list[str]:
    tokens = shlex.split(command)
    normalized = _normalize_devflow_command_tokens(tokens)
    if len(normalized) < 6 or normalized[1:3] != ["task", "run"]:
        raise ValueError("only approved shell worker runs may run from the operating layer")
    task_id = normalized[3]
    if not task_id or task_id.startswith("-"):
        raise ValueError("shell worker run requires a task id")
    if "--" not in normalized:
        raise ValueError("approved browser shell worker run requires a command after '--'")
    separator = normalized.index("--")
    options = normalized[4:separator]
    command_tokens = normalized[separator + 1 :]
    worker = None
    index = 0
    while index < len(options):
        token = options[index]
        if token == "--worker":
            if index + 1 >= len(options):
                raise ValueError("approved browser shell worker run requires --worker shell")
            worker = options[index + 1]
            index += 2
            continue
        if token == "--project":
            if index + 1 >= len(options) or options[index + 1].startswith("-"):
                raise ValueError("approved browser shell worker run requires a project id after --project")
            index += 2
            continue
        if token == "--timeout-seconds":
            if index + 1 >= len(options) or not options[index + 1].isdigit():
                raise ValueError("approved browser shell worker run requires a numeric --timeout-seconds value")
            index += 2
            continue
        raise ValueError("approved browser shell worker run allows only --project, --worker shell, and --timeout-seconds")
    if worker != "shell":
        raise ValueError("browser worker execution is limited to --worker shell")
    shell_command = " ".join(command_tokens).strip()
    if _is_placeholder_text(shell_command, field="command"):
        raise ValueError("approved browser shell worker run requires a concrete command")
    if _looks_like_provider_or_local_model_command(command_tokens):
        raise ValueError("provider and local-model commands cannot run from the browser shell-worker path")
    return _devflow_command_args_from_tokens(tokens)


def _approved_task_verification_command_args(command: str) -> list[str]:
    tokens = shlex.split(command)
    normalized = _normalize_devflow_command_tokens(tokens)
    if len(normalized) < 5 or normalized[1:3] != ["task", "verify"]:
        raise ValueError("only approved task verification may run from the operating layer")
    task_id = normalized[3]
    if not task_id or task_id.startswith("-"):
        raise ValueError("task verification command requires a task id")
    if "--shell" not in normalized:
        raise ValueError('approved browser verification requires --shell "<command>"')
    shell_index = normalized.index("--shell")
    if shell_index + 1 >= len(normalized):
        raise ValueError('approved browser verification requires --shell "<command>"')
    shell_command = normalized[shell_index + 1].strip()
    if not shell_command or shell_command == "<command>":
        raise ValueError("approved browser verification requires a concrete shell command")
    return _devflow_command_args_from_tokens(tokens)


def _approved_task_promotion_command_args(command: str) -> list[str]:
    tokens = shlex.split(command)
    normalized = _normalize_devflow_command_tokens(tokens)
    if len(normalized) < 4 or normalized[1:3] != ["task", "promote"]:
        raise ValueError("only approved task promotion may run from the operating layer")
    task_id = normalized[3]
    if not task_id or task_id.startswith("-"):
        raise ValueError("task promotion command requires a task id")
    allowed_options = {"--project"}
    index = 4
    while index < len(normalized):
        token = normalized[index]
        if token not in allowed_options:
            raise ValueError("approved browser promotion allows only the optional --project flag")
        if token == "--project":
            if index + 1 >= len(normalized) or normalized[index + 1].startswith("-"):
                raise ValueError("approved browser promotion requires a project id after --project")
            index += 2
            continue
        index += 1
    return _devflow_command_args_from_tokens(tokens)


def _approved_agent_add_provider_command_args(command: str) -> list[str]:
    tokens = shlex.split(command)
    normalized = _normalize_devflow_command_tokens(tokens)
    if len(normalized) < 4 or normalized[1:3] != ["agent", "add-provider"]:
        raise ValueError("only approved agent add-provider may run from the operating layer")
    provider_id = normalized[3]
    if _is_placeholder_text(provider_id, field="provider"):
        raise ValueError("approved provider onboarding requires a concrete provider id")
    values = _parse_exact_options(
        normalized[4:],
        value_options={"--adapter", "--base-url", "--api-key-env", "--timeout-seconds"},
        flags={"--json"},
        command_label="approved provider onboarding",
    )
    if "--adapter" not in values or "--base-url" not in values:
        raise ValueError("approved provider onboarding requires --adapter and --base-url")
    if _is_placeholder_text(values["--adapter"], field="adapter"):
        raise ValueError("approved provider onboarding requires a concrete adapter")
    if _is_placeholder_text(values["--base-url"], field="url"):
        raise ValueError("approved provider onboarding requires a concrete base URL")
    if "--timeout-seconds" in values and not values["--timeout-seconds"].isdigit():
        raise ValueError("approved provider onboarding requires a numeric --timeout-seconds value")
    return _devflow_command_args_from_tokens(tokens)


def _approved_agent_add_model_command_args(command: str) -> list[str]:
    tokens = shlex.split(command)
    normalized = _normalize_devflow_command_tokens(tokens)
    if len(normalized) < 3 or normalized[1:3] != ["agent", "add-model"]:
        raise ValueError("only approved agent add-model may run from the operating layer")
    values = _parse_exact_options(
        normalized[3:],
        value_options={"--provider", "--model", "--authority", "--role", "--profile-id"},
        flags={"--json"},
        command_label="approved model onboarding",
    )
    for option in ("--provider", "--model", "--authority", "--role"):
        if option not in values:
            raise ValueError(f"approved model onboarding requires {option}")
    if values["--authority"] not in {"read-only", "advisory", "patch-proposer", "disabled"}:
        raise ValueError("approved model onboarding authority must be read-only, advisory, patch-proposer, or disabled")
    for option, field in (("--provider", "provider"), ("--model", "model"), ("--role", "role")):
        if _is_placeholder_text(values[option], field=field):
            raise ValueError(f"approved model onboarding requires a concrete {field}")
    return _devflow_command_args_from_tokens(tokens)


def _approved_agent_propose_patch_command_args(command: str) -> list[str]:
    tokens = shlex.split(command)
    normalized = _normalize_devflow_command_tokens(tokens)
    if len(normalized) < 3 or normalized[1:3] != ["agent", "propose-patch"]:
        raise ValueError("only approved agent propose-patch may run from the operating layer")
    values = _parse_exact_options(
        normalized[3:],
        value_options={"--task", "--profile"},
        flags={"--json"},
        command_label="approved patch-proposal model run",
    )
    if "--task" not in values or "--profile" not in values:
        raise ValueError("approved patch proposal requires --task and --profile")
    if _is_placeholder_text(values["--task"], field="task-id") or _is_placeholder_text(values["--profile"], field="profile"):
        raise ValueError("approved patch proposal requires concrete task and profile ids")
    return _devflow_command_args_from_tokens(tokens)


def _approved_agent_serial_packet_command_args(command: str) -> list[str]:
    tokens = shlex.split(command)
    normalized = _normalize_devflow_command_tokens(tokens)
    if len(normalized) < 3 or normalized[1:3] != ["agent", "serial-packet"]:
        raise ValueError("only approved serial local-agent packet creation may run from the operating layer")
    values = _parse_repeated_serial_packet_options(normalized[3:])
    required_values = {
        "--phase": "phase",
        "--provider": "provider",
        "--model": "model",
        "--task-id": "task-id",
        "--worker-id": "worker-id",
        "--runtime": "runtime",
        "--hermes-profile": "profile",
    }
    for option, field in required_values.items():
        value = values["single"].get(option, "")
        if _is_placeholder_text(value, field=field) or _has_template_placeholder(value):
            raise ValueError(f"approved serial packet creation requires a concrete {field}")
    if values["single"]["--runtime"] != "hermes-profile":
        raise ValueError("browser serial packet creation is limited to --runtime hermes-profile")
    if not values["repeated"].get("--allowed-file"):
        raise ValueError("approved serial packet creation requires at least one --allowed-file")
    if not values["repeated"].get("--verify"):
        raise ValueError("approved serial packet creation requires at least one --verify command")
    for option, field in (("--allowed-file", "allowed file"), ("--verify", "verification command")):
        for value in values["repeated"].get(option, []):
            if _has_template_placeholder(value) or not value.strip():
                raise ValueError(f"approved serial packet creation requires a concrete {field}")
    for toolset in values["repeated"].get("--toolset", []):
        if _has_template_placeholder(toolset) or not toolset.strip() or toolset.startswith("-"):
            raise ValueError("approved serial packet creation requires concrete toolset names")
    return _devflow_command_args_from_tokens(tokens)


def _parse_repeated_serial_packet_options(tokens: list[str]) -> dict[str, object]:
    single_value_options = {
        "--phase",
        "--provider",
        "--model",
        "--mission",
        "--run-id",
        "--task-id",
        "--worker-id",
        "--runtime",
        "--hermes-profile",
    }
    repeated_value_options = {"--allowed-file", "--verify", "--toolset"}
    flags: set[str] = set()
    single: dict[str, str] = {}
    repeated: dict[str, list[str]] = {option: [] for option in repeated_value_options}
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token in flags:
            index += 1
            continue
        if token in single_value_options or token in repeated_value_options:
            if index + 1 >= len(tokens) or tokens[index + 1].startswith("-"):
                raise ValueError(f"approved serial packet creation requires a value after {token}")
            value = tokens[index + 1]
            if token in single_value_options:
                single[token] = value
            else:
                repeated.setdefault(token, []).append(value)
            index += 2
            continue
        if token.startswith("-"):
            allowed = ", ".join(sorted(single_value_options | repeated_value_options | flags))
            raise ValueError(f"approved serial packet creation allows only {allowed}")
        raise ValueError(f"approved serial packet creation does not allow positional value '{token}'")
    return {"single": single, "repeated": repeated}


def _has_template_placeholder(value: str) -> bool:
    return bool(re.search(r"<[^>]+>", value))


def _parse_exact_options(
    tokens: list[str],
    *,
    value_options: set[str],
    flags: set[str],
    command_label: str,
) -> dict[str, str]:
    values: dict[str, str] = {}
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token in flags:
            index += 1
            continue
        if token in value_options:
            if index + 1 >= len(tokens) or tokens[index + 1].startswith("-"):
                raise ValueError(f"{command_label} requires a value after {token}")
            values[token] = tokens[index + 1]
            index += 2
            continue
        if token.startswith("-"):
            allowed = ", ".join(sorted(value_options | flags))
            raise ValueError(f"{command_label} allows only {allowed}")
        raise ValueError(f"{command_label} does not allow positional value '{token}'")
    return values


def _approval_payload_matches(payload: dict[str, object], command: str) -> bool:
    if payload.get("human_approved") is not True:
        return False
    if payload.get("approval_phrase") != ACTION_APPROVAL_PHRASE:
        return False
    if payload.get("approved_command") != command:
        return False
    return True


def _is_placeholder_text(value: str, *, field: str) -> bool:
    normalized = " ".join(value.strip().lower().split())
    placeholders = {
        "",
        "...",
        "todo",
        "tbd",
        "placeholder",
        f"<{field}>",
        field,
    }
    if field == "command":
        placeholders.update({"your command", "run command", "shell command"})
    if field == "idea":
        placeholders.update({"your idea", "rough idea", "brainstorm", "brainstorm here"})
    if field == "title":
        placeholders.update({"task title", "untitled", "new task"})
    if field == "definition-of-done":
        placeholders.update({"definition of done", "done criteria", "completion criteria", "your definition of done"})
    if field in {"provider", "model", "profile", "task-id", "adapter", "url", "role"}:
        placeholders.update({
            f"<{field}>",
            field.replace("-", " "),
            f"your {field}",
            f"{field} id",
            f"{field}-id",
        })
    return normalized in placeholders


def _looks_like_provider_or_local_model_command(command_tokens: list[str]) -> bool:
    if not command_tokens:
        return False
    lowered = [token.lower() for token in command_tokens]
    joined = " ".join(lowered)
    if lowered[:3] == ["devflow", "task", "local"]:
        return True
    if lowered[:3] == ["devflow", "agent", "run"]:
        return True
    if lowered[:3] == ["devflow", "agent", "advise"]:
        return True
    if lowered[:3] == ["devflow", "agent", "propose-patch"]:
        return True
    if lowered[:3] == ["devflow", "agent", "add-model"]:
        return True
    if lowered[:3] == ["devflow", "agent", "add-provider"]:
        return True
    provider_markers = (
        "ollama",
        "openai",
        "anthropic",
        "gemini",
        "claude",
        "aider",
        "opencode",
        "qwen",
        "qwopus",
        "gemma",
    )
    return any(marker in joined for marker in provider_markers)


def _devflow_command_args_from_tokens(tokens: list[str]) -> list[str]:
    normalized = _normalize_devflow_command_tokens(tokens)
    if not normalized:
        raise ValueError("command is required")
    if normalized[0] == "devflow":
        return [sys.executable, "-m", "devflow", *normalized[1:]]
    raise ValueError("only devflow commands may run from the operating layer")


def _normalize_devflow_command_tokens(tokens: list[str]) -> list[str]:
    if tokens and tokens[0] == "run":
        tokens = tokens[1:]
    if not tokens:
        return []
    if len(tokens) >= 4 and tokens[1:3] == ["-m", "devflow.cli"]:
        return ["devflow", *tokens[3:]]
    return tokens


_BROWSER_ACTION_RULES: tuple[_BrowserActionRule, ...] = (
    _BrowserActionRule(APPROVAL_REQUIRED_EVIDENCE_WRITING, _approved_idea_capture_command_args),
    _BrowserActionRule(APPROVAL_REQUIRED_EVIDENCE_WRITING, _approved_idea_evidence_command_args),
    _BrowserActionRule(APPROVAL_REQUIRED_EVIDENCE_WRITING, _approved_idea_classify_command_args),
    _BrowserActionRule(APPROVAL_REQUIRED_EVIDENCE_WRITING, _approved_architecture_refresh_command_args),
    _BrowserActionRule(APPROVAL_REQUIRED_EVIDENCE_WRITING, _approved_agent_serial_packet_command_args),
    _BrowserActionRule(APPROVAL_REQUIRED_TASK_STATE, _approved_task_creation_command_args),
    _BrowserActionRule(APPROVAL_REQUIRED_TASK_STATE, _approved_task_close_command_args),
    _BrowserActionRule(APPROVAL_REQUIRED_TASK_STATE, _approved_cleanup_preview_command_args),
    _BrowserActionRule(APPROVAL_REQUIRED_TASK_STATE, _approved_agent_add_provider_command_args),
    _BrowserActionRule(APPROVAL_REQUIRED_TASK_STATE, _approved_agent_add_model_command_args),
    _BrowserActionRule(APPROVAL_REQUIRED_WORKER_RUNTIME, _approved_shell_worker_run_command_args),
    _BrowserActionRule(APPROVAL_REQUIRED_WORKER_RUNTIME, _approved_task_verification_command_args),
    _BrowserActionRule(APPROVAL_REQUIRED_WORKER_RUNTIME, _approved_agent_propose_patch_command_args),
    _BrowserActionRule(APPROVAL_REQUIRED_GIT, _approved_task_promotion_command_args, writes_promotion_context=True),
)


__all__ = [
    "ACTION_APPROVAL_PHRASE",
    "BROWSER_ALLOWED_MUTATIONS",
    "BROWSER_BLOCKED_MUTATIONS",
    "BrowserActionCommand",
    "get_browser_allowed_mutations",
    "get_browser_blocked_mutations",
    "promotion_task_id_from_command",
    "resolve_browser_action_command",
]
