"""Tests for the `devflow supervisor classify` CLI subcommand.

Tests exercise the CLI endpoint across all six safety classes:
- pure_read_only
- approval_required_evidence_writing
- approval_required_task_state
- approval_required_worker_runtime
- approval_required_git
- forbidden_for_supervisor
"""
from __future__ import annotations

import json

from typer.testing import CliRunner

from devflow.cli import app
from devflow.control_room.supervisor_surface import (
    APPROVAL_REQUIRED_EVIDENCE_WRITING,
    APPROVAL_REQUIRED_GIT,
    APPROVAL_REQUIRED_TASK_STATE,
    APPROVAL_REQUIRED_WORKER_RUNTIME,
    FORBIDDEN_FOR_SUPERVISOR,
    PURE_READ_ONLY,
    classify_supervisor_command,
)

runner = CliRunner()


def _json_output(result) -> dict:
    """Parse the CLI JSON output and verify the endpoint succeeded."""
    assert result.exit_code == 0, result.output
    return json.loads(result.output)


# ---------------------------------------------------------------------------
# Pure-read-only commands
# ---------------------------------------------------------------------------

class TestClassifyReadOnly:
    """Commands that may be auto-run without human approval."""

    def test_devflow_doctor(self):
        result = runner.invoke(app, ["supervisor", "classify", "devflow doctor", "--json"])
        payload = _json_output(result)
        assert payload["safety_class"] == PURE_READ_ONLY
        assert payload["requires_human_approval"] is False
        assert payload["supervisor_may_auto_run"] is True
        assert payload["why_not_auto_runnable"] is None

    def test_devflow_status_json(self):
        result = runner.invoke(app, ["supervisor", "classify", "devflow status --json", "--json"])
        payload = _json_output(result)
        assert payload["safety_class"] == PURE_READ_ONLY
        assert payload["supervisor_may_auto_run"] is True

    def test_devflow_supervisor(self):
        result = runner.invoke(app, ["supervisor", "classify", "devflow supervisor policy --json", "--json"])
        payload = _json_output(result)
        assert payload["safety_class"] == PURE_READ_ONLY
        assert payload["supervisor_may_auto_run"] is True

    def test_devflow_git_status(self):
        result = runner.invoke(app, ["supervisor", "classify", "devflow git status", "--json"])
        payload = _json_output(result)
        assert payload["safety_class"] == PURE_READ_ONLY
        assert payload["supervisor_may_auto_run"] is True

    def test_devflow_task_list(self):
        result = runner.invoke(app, ["supervisor", "classify", "devflow task list", "--json"])
        payload = _json_output(result)
        assert payload["safety_class"] == PURE_READ_ONLY

    def test_devflow_task_promote_preview(self):
        result = runner.invoke(app, ["supervisor", "classify", "devflow task promote-preview task-0001", "--json"])
        payload = _json_output(result)
        assert payload["safety_class"] == PURE_READ_ONLY

    def test_devflow_task_cleanup_dry_run(self):
        result = runner.invoke(app, ["supervisor", "classify", "devflow task cleanup task-0001 --dry-run", "--json"])
        payload = _json_output(result)
        assert payload["safety_class"] == PURE_READ_ONLY

    def test_devflow_project_list(self):
        result = runner.invoke(app, ["supervisor", "classify", "devflow project list", "--json"])
        payload = _json_output(result)
        assert payload["safety_class"] == PURE_READ_ONLY

    def test_devflow_goal_read_commands(self):
        for command in (
            "devflow goal list",
            "devflow goal show G-0001",
            "devflow goal status G-0001",
            "devflow goal next G-0001",
            "devflow goal slices G-0001",
        ):
            result = runner.invoke(app, ["supervisor", "classify", command, "--json"])
            payload = _json_output(result)
            assert payload["safety_class"] == PURE_READ_ONLY
            assert payload["supervisor_may_auto_run"] is True


# ---------------------------------------------------------------------------
# Approval-required: evidence writing
# ---------------------------------------------------------------------------

class TestClassifyEvidenceWriting:
    """Commands that write derived evidence, patches, packets, and should need approval."""

    def test_task_review_patch(self):
        result = runner.invoke(app, ["supervisor", "classify", "devflow task review-patch task-0001", "--json"])
        payload = _json_output(result)
        assert payload["safety_class"] == APPROVAL_REQUIRED_EVIDENCE_WRITING
        assert payload["requires_human_approval"] is True
        assert payload["supervisor_may_auto_run"] is False

    def test_task_patch_dry_run(self):
        result = runner.invoke(app, ["supervisor", "classify", "devflow task patch-dry-run task-0001", "--json"])
        payload = _json_output(result)
        assert payload["safety_class"] == APPROVAL_REQUIRED_EVIDENCE_WRITING
        assert payload["requires_human_approval"] is True

    def test_task_packet_save(self):
        result = runner.invoke(app, ["supervisor", "classify", "devflow task packet task-0001 --save", "--json"])
        payload = _json_output(result)
        assert payload["safety_class"] == APPROVAL_REQUIRED_EVIDENCE_WRITING


# ---------------------------------------------------------------------------
# Agent inventory and local-model dry-run routing
# ---------------------------------------------------------------------------

class TestClassifyAgentCommands:
    """Hermes needs read-only agent inventory and dry-run previews before approved model runs."""

    def test_agent_inventory_commands_are_read_only(self):
        for command in (
            "devflow agent list --json",
            "devflow agent show local-gemma4-summarizer --json",
            "devflow agent policy --json",
            "devflow agent packet task-0001 devflow-manual-codex-worker",
        ):
            result = runner.invoke(app, ["supervisor", "classify", command, "--json"])
            payload = _json_output(result)
            assert payload["safety_class"] == PURE_READ_ONLY
            assert payload["requires_human_approval"] is False
            assert payload["supervisor_may_auto_run"] is True

    def test_agent_dry_run_is_read_only_but_real_run_requires_approval(self):
        dry_run = runner.invoke(
            app,
            [
                "supervisor",
                "classify",
                "devflow agent run --task task-0001 --profile local-gemma4-summarizer --dry-run --json",
                "--json",
            ],
        )
        dry_payload = _json_output(dry_run)
        assert dry_payload["safety_class"] == PURE_READ_ONLY
        assert dry_payload["supervisor_may_auto_run"] is True

        real_run = runner.invoke(
            app,
            [
                "supervisor",
                "classify",
                "devflow agent run --task task-0001 --profile local-gemma4-summarizer --json",
                "--json",
            ],
        )
        real_payload = _json_output(real_run)
        assert real_payload["safety_class"] == APPROVAL_REQUIRED_WORKER_RUNTIME
        assert real_payload["requires_human_approval"] is True

    def test_agent_advise_is_dry_run_read_only_and_real_run_is_model_runtime(self):
        dry_run = runner.invoke(
            app,
            [
                "supervisor",
                "classify",
                "devflow agent advise --profile deepseek-v4-flash-planner --job gap-analysis --dry-run --json",
                "--json",
            ],
        )
        dry_payload = _json_output(dry_run)
        assert dry_payload["safety_class"] == PURE_READ_ONLY
        assert dry_payload["supervisor_may_auto_run"] is True

        real_run = runner.invoke(
            app,
            [
                "supervisor",
                "classify",
                "devflow agent advise --profile deepseek-v4-flash-planner --job gap-analysis --json",
                "--json",
            ],
        )
        real_payload = _json_output(real_run)
        assert real_payload["safety_class"] == APPROVAL_REQUIRED_WORKER_RUNTIME
        assert real_payload["requires_human_approval"] is True

    def test_agent_propose_patch_requires_explicit_human_approval(self):
        result = runner.invoke(
            app,
            [
                "supervisor",
                "classify",
                "devflow agent propose-patch --task task-0001 --profile deepseek-v4-pro-patch-proposer --json",
                "--json",
            ],
        )
        payload = _json_output(result)
        assert payload["safety_class"] == APPROVAL_REQUIRED_WORKER_RUNTIME
        assert payload["requires_human_approval"] is True
        assert payload["supervisor_may_auto_run"] is False

    def test_serial_packet_is_evidence_writing_and_hermes_run_boundary_is_explicit(self):
        serial_packet = runner.invoke(
            app,
            [
                "supervisor",
                "classify",
                "devflow agent serial-packet --phase implementer --provider ollama --model qwen3.6:latest --task-id task-0001 --worker-id qwen-worker --runtime hermes-profile --hermes-profile qwen-worker --allowed-file src/foo.py --verify 'pytest tests/foo.py -q'",
                "--json",
            ],
        )
        packet_payload = _json_output(serial_packet)
        assert packet_payload["safety_class"] == APPROVAL_REQUIRED_EVIDENCE_WRITING
        assert packet_payload["requires_human_approval"] is True
        assert packet_payload["supervisor_may_auto_run"] is False

        dry_run = runner.invoke(
            app,
            [
                "supervisor",
                "classify",
                "devflow agent hermes-run serial-123 --profile qwen-worker --dry-run --json",
                "--json",
            ],
        )
        dry_payload = _json_output(dry_run)
        assert dry_payload["safety_class"] == PURE_READ_ONLY
        assert dry_payload["requires_human_approval"] is False
        assert dry_payload["supervisor_may_auto_run"] is True

        live_launch = runner.invoke(
            app,
            [
                "supervisor",
                "classify",
                "devflow agent hermes-run serial-123 --profile qwen-worker --json",
                "--json",
            ],
        )
        launch_payload = _json_output(live_launch)
        assert launch_payload["safety_class"] == APPROVAL_REQUIRED_WORKER_RUNTIME
        assert launch_payload["requires_human_approval"] is True
        assert launch_payload["supervisor_may_auto_run"] is False

    def test_agent_catalog_and_onboarding_commands_have_bounded_policy(self):
        catalog = runner.invoke(
            app,
            ["supervisor", "classify", "devflow agent catalog --json", "--json"],
        )
        catalog_payload = _json_output(catalog)
        assert catalog_payload["safety_class"] == PURE_READ_ONLY

        dry_provider = runner.invoke(
            app,
            [
                "supervisor",
                "classify",
                "devflow agent add-provider local_gateway --adapter openai_compatible --base-url http://127.0.0.1:8000/v1 --dry-run --json",
                "--json",
            ],
        )
        assert _json_output(dry_provider)["safety_class"] == PURE_READ_ONLY

        add_provider = runner.invoke(
            app,
            [
                "supervisor",
                "classify",
                "devflow agent add-provider local_gateway --adapter openai_compatible --base-url http://127.0.0.1:8000/v1 --json",
                "--json",
            ],
        )
        add_provider_payload = _json_output(add_provider)
        assert add_provider_payload["safety_class"] == APPROVAL_REQUIRED_TASK_STATE
        assert add_provider_payload["requires_human_approval"] is True

        add_model = runner.invoke(
            app,
            [
                "supervisor",
                "classify",
                "devflow agent add-model --provider ollama --model llama3.2:latest --authority read-only --role local_senior_worker --json",
                "--json",
            ],
        )
        add_model_payload = _json_output(add_model)
        assert add_model_payload["safety_class"] == APPROVAL_REQUIRED_TASK_STATE
        assert add_model_payload["requires_human_approval"] is True


# ---------------------------------------------------------------------------
# Approval-required: task state mutation
# ---------------------------------------------------------------------------

class TestClassifyTaskState:
    """Commands that create, close, finalize, or otherwise mutate Dev-Flow state."""

    def test_task_create(self):
        result = runner.invoke(app, ["supervisor", "classify", "devflow task create example", "--json"])
        payload = _json_output(result)
        assert payload["safety_class"] == APPROVAL_REQUIRED_TASK_STATE
        assert payload["requires_human_approval"] is True
        assert payload["supervisor_may_auto_run"] is False

    def test_task_close(self):
        result = runner.invoke(
            app, ["supervisor", "classify", "devflow task close task-0001 --outcome duplicate", "--json"]
        )
        payload = _json_output(result)
        assert payload["safety_class"] == APPROVAL_REQUIRED_TASK_STATE

    def test_task_finalize(self):
        result = runner.invoke(app, ["supervisor", "classify", "devflow task finalize task-0001", "--json"])
        payload = _json_output(result)
        assert payload["safety_class"] == APPROVAL_REQUIRED_TASK_STATE

    def test_task_apply_patch(self):
        result = runner.invoke(app, ["supervisor", "classify", "devflow task apply-patch task-0001", "--json"])
        payload = _json_output(result)
        assert payload["safety_class"] == APPROVAL_REQUIRED_TASK_STATE

    def test_task_cleanup_without_dry_run(self):
        result = runner.invoke(app, ["supervisor", "classify", "devflow task cleanup task-0001 --apply", "--json"])
        payload = _json_output(result)
        assert payload["safety_class"] == APPROVAL_REQUIRED_TASK_STATE

    def test_task_prune_closed_apply(self):
        result = runner.invoke(
            app,
            ["supervisor", "classify", "devflow task prune-closed --apply --older-than 30d", "--json"],
        )
        payload = _json_output(result)
        assert payload["safety_class"] == APPROVAL_REQUIRED_TASK_STATE

    def test_project_create(self):
        result = runner.invoke(
            app,
            ["supervisor", "classify", "devflow project create telegram-smoke-test --source-control none", "--json"],
        )
        payload = _json_output(result)
        assert payload["safety_class"] == APPROVAL_REQUIRED_TASK_STATE

    def test_goal_state_commands(self):
        for command in (
            "devflow goal init brief.md",
            "devflow goal create-task G-0001 TS-0001",
        ):
            result = runner.invoke(app, ["supervisor", "classify", command, "--json"])
            payload = _json_output(result)
            assert payload["safety_class"] == APPROVAL_REQUIRED_TASK_STATE
            assert payload["requires_human_approval"] is True


# ---------------------------------------------------------------------------
# Approval-required: worker runtime
# ---------------------------------------------------------------------------

class TestClassifyWorkerRuntime:
    """Commands that run workers, agents, or verification."""

    def test_supervise(self):
        result = runner.invoke(app, ["supervisor", "classify", "devflow supervise", "--json"])
        payload = _json_output(result)
        assert payload["safety_class"] == APPROVAL_REQUIRED_WORKER_RUNTIME
        assert payload["requires_human_approval"] is True
        assert payload["supervisor_may_auto_run"] is False

    def test_task_run(self):
        result = runner.invoke(
            app, ["supervisor", "classify", "devflow task run task-0001 --worker shell -- echo hi", "--json"]
        )
        payload = _json_output(result)
        assert payload["safety_class"] == APPROVAL_REQUIRED_WORKER_RUNTIME

    def test_task_local(self):
        result = runner.invoke(app, ["supervisor", "classify", "devflow task local task-0001", "--json"])
        payload = _json_output(result)
        assert payload["safety_class"] == APPROVAL_REQUIRED_WORKER_RUNTIME


# ---------------------------------------------------------------------------
# Approval-required: promotion / Git
# ---------------------------------------------------------------------------

class TestClassifyGitPromotion:
    """Commands that affect branches, commits, pushes, or promotion."""

    def test_task_promote(self):
        result = runner.invoke(app, ["supervisor", "classify", "devflow task promote task-0001", "--json"])
        payload = _json_output(result)
        assert payload["safety_class"] == APPROVAL_REQUIRED_GIT
        assert payload["requires_human_approval"] is True
        assert payload["supervisor_may_auto_run"] is False

    def test_push_main(self):
        result = runner.invoke(app, ["supervisor", "classify", "devflow push-main", "--json"])
        payload = _json_output(result)
        assert payload["safety_class"] == APPROVAL_REQUIRED_GIT

    def test_sync_main(self):
        result = runner.invoke(app, ["supervisor", "classify", "devflow sync-main", "--json"])
        payload = _json_output(result)
        assert payload["safety_class"] == APPROVAL_REQUIRED_GIT

    def test_branch_archive(self):
        result = runner.invoke(app, ["supervisor", "classify", "devflow branch archive feat/x", "--json"])
        payload = _json_output(result)
        assert payload["safety_class"] == APPROVAL_REQUIRED_GIT

    def test_project_connect_github(self):
        result = runner.invoke(
            app,
            [
                "supervisor",
                "classify",
                "devflow project connect-github telegram-smoke-test --remote-url https://github.com/example/repo",
                "--json",
            ],
        )
        payload = _json_output(result)
        assert payload["safety_class"] == APPROVAL_REQUIRED_GIT


# ---------------------------------------------------------------------------
# Forbidden
# ---------------------------------------------------------------------------

class TestClassifyForbidden:
    """Commands that are not recognized by the supervisor policy."""

    def test_unknown_command(self):
        result = runner.invoke(app, ["supervisor", "classify", "devflow task teleport task-0001", "--json"])
        payload = _json_output(result)
        assert payload["safety_class"] == FORBIDDEN_FOR_SUPERVISOR
        assert payload["requires_human_approval"] is True
        assert payload["supervisor_may_auto_run"] is False

    def test_direct_git(self):
        result = runner.invoke(app, ["supervisor", "classify", "git commit -am unsafe", "--json"])
        payload = _json_output(result)
        assert payload["safety_class"] == FORBIDDEN_FOR_SUPERVISOR
        assert payload["supervisor_may_auto_run"] is False

    def test_direct_source_edit(self):
        result = runner.invoke(app, ["supervisor", "classify", "vim src/devflow/cli.py", "--json"])
        payload = _json_output(result)
        assert payload["safety_class"] == FORBIDDEN_FOR_SUPERVISOR

    def test_unknown_binary(self):
        result = runner.invoke(app, ["supervisor", "classify", "python -m pytest --run", "--json"])
        payload = _json_output(result)
        assert payload["safety_class"] == FORBIDDEN_FOR_SUPERVISOR

    def test_empty_command(self):
        result = runner.invoke(app, ["supervisor", "classify", "", "--json"])
        payload = _json_output(result)
        assert payload["safety_class"] == FORBIDDEN_FOR_SUPERVISOR

    def test_agent_run(self):
        result = runner.invoke(app, ["supervisor", "classify", "devflow agent run --task task-0001", "--json"])
        payload = _json_output(result)
        assert payload["safety_class"] == APPROVAL_REQUIRED_WORKER_RUNTIME
        assert payload["requires_human_approval"] is True
        assert payload["supervisor_may_auto_run"] is False


# ---------------------------------------------------------------------------
# JSON output fields verified programmatically
# ---------------------------------------------------------------------------

def test_all_classification_fields_present():
    """Every classification result must contain all four required fields."""
    test_commands = [
        "devflow doctor",
        "devflow task create x",
        "devflow supervise",
        "devflow task promote t1",
        "git commit",
    ]
    for cmd in test_commands:
        result = runner.invoke(app, ["supervisor", "classify", cmd, "--json"]).exit_code
        classification = classify_supervisor_command(cmd)
        assert classification["safety_class"] is not None
        assert isinstance(classification["requires_human_approval"], bool)
        assert isinstance(classification["supervisor_may_auto_run"], bool)
        assert classification["why_not_auto_runnable"] is None or isinstance(
            classification["why_not_auto_runnable"], str
        )


def test_cli_json_output_is_valid_json():
    """The CLI --json output must be parseable as JSON for every safety class."""
    cmd_by_class = {
        PURE_READ_ONLY: "devflow doctor",
        APPROVAL_REQUIRED_EVIDENCE_WRITING: "devflow task review-patch task-0001",
        APPROVAL_REQUIRED_TASK_STATE: "devflow task create example",
        APPROVAL_REQUIRED_WORKER_RUNTIME: "devflow task run task-0001 --worker shell -- echo hi",
        APPROVAL_REQUIRED_GIT: "devflow task promote task-0001",
        FORBIDDEN_FOR_SUPERVISOR: "git commit -am x",
    }
    for safety_class, cmd in cmd_by_class.items():
        result = runner.invoke(app, ["supervisor", "classify", cmd, "--json"])
        assert result.exit_code == 0, f"CLI failed for {cmd}: {result.output}"
        payload = json.loads(result.output)
        assert payload["safety_class"] == safety_class
        # supervisor_may_auto_run is True exactly when safety_class is PURE_READ_ONLY
        assert payload["supervisor_may_auto_run"] == (safety_class == PURE_READ_ONLY)
        # requires_human_approval is True exactly when safety_class != PURE_READ_ONLY
        assert payload["requires_human_approval"] != (safety_class == PURE_READ_ONLY)
        # why_not_auto_runnable is None exactly when supervisor_may_auto_run is True
        assert (payload["why_not_auto_runnable"] is None) == payload["supervisor_may_auto_run"]
