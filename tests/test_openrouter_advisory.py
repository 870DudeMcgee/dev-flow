from __future__ import annotations

import json
import subprocess
import urllib.request
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from devflow.cli import app
from devflow.control_room.patch_proposal import normalize_hunk_line_counts
from tests.helpers import setup_temp_git_repo


runner = CliRunner()
ADVISORY_PROFILE_ID = "hermes-qwen37plus"
ADVISORY_MODEL = "qwen/qwen3.7-plus"
REVIEW_PROFILE_ID = "hermes-sonnet46"
PATCH_PROFILE_ID = "test-patch-proposal-surface"
PATCH_MODEL = "minimax/minimax-m3"


class MockResponse:
    def __init__(self, body: dict[str, Any]) -> None:
        self.body = json.dumps(body).encode("utf-8")

    def read(self, *args: Any, **kwargs: Any) -> bytes:
        return self.body

    def __enter__(self) -> "MockResponse":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        return None


def _write_test_patch_surface_profile(root: Path) -> None:
    registry_path = root / ".devflow/agents/registry.yaml"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(
        f"""version: 1
default_agent: devflow-manual-codex-worker
agents:
  {PATCH_PROFILE_ID}:
    provider: openrouter
    model: {PATCH_MODEL}
    adapter: openai_compatible
    role: implementation_worker
    tier: frontier
    default_mode: patch_proposal_only
    execution_mode: automated
    purpose: Test-only patch proposal execution surface; production model profiles stay capability identities.
    model_role_name: test patch proposal surface
    secondary_roles:
      - patch-proposal-surface
      - test-only
    use_caution:
      - Writes patch proposal evidence only; Dev-Flow review, dry-run, apply, verification, and promotion gates remain required.
    workspace: isolated_task_workspace
    can_see:
      - task_packet
      - assigned_workspace
      - recent_events
      - verification_plan
    can_touch:
      - <task>/agents/{PATCH_PROFILE_ID}/proposal.patch
      - <task>/agents/{PATCH_PROFILE_ID}/raw_output.md
      - <task>/agents/{PATCH_PROFILE_ID}/run.json
      - <task>/agents/{PATCH_PROFILE_ID}/result.md
    cannot_touch:
      - <main_checkout>/**
      - <workspace>/**
      - <task>/task.yaml
      - <task>/events.jsonl
      - <task>/verification.json
      - <task>/merge-readiness.json
      - .git/**
    allowed_reads:
      - <task>/packet.json
      - <task>/events.jsonl
      - <task>/questions.jsonl
      - <workspace>/**
    allowed_writes:
      - <task>/agents/{PATCH_PROFILE_ID}/proposal.patch
      - <task>/agents/{PATCH_PROFILE_ID}/raw_output.md
      - <task>/agents/{PATCH_PROFILE_ID}/run.json
      - <task>/agents/{PATCH_PROFILE_ID}/result.md
    forbidden_writes:
      - <main_checkout>/**
      - <workspace>/**
      - <task>/task.yaml
      - <task>/events.jsonl
      - <task>/verification.json
      - <task>/merge-readiness.json
      - <task>/packet.json
      - .git/**
    required_outputs:
      - Write proposal.patch, raw_output.md, run.json, and result.md under the task-local agent directory.
      - Do not apply patches, verify, promote, commit, merge, or push.
    completion_rules:
      - Run only by explicit human-selected propose-patch command.
      - Treat proposal.patch as evidence until review, dry-run, apply, verification, and promotion gates pass.
    can_run_shell: false
    can_use_network: false
    can_promote: false
    hermes_delegable: false
    enabled: true
""",
        encoding="utf-8",
    )


def test_agent_advise_dry_run_does_not_call_openrouter_or_write_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    def fail_urlopen(req: urllib.request.Request, timeout: float | None = None) -> MockResponse:
        raise AssertionError("dry-run must not call OpenRouter")

    monkeypatch.setattr(urllib.request, "urlopen", fail_urlopen)

    result = runner.invoke(
        app,
        [
            "agent",
            "advise",
            "--profile",
            ADVISORY_PROFILE_ID,
            "--job",
            "gap-analysis",
            "--dry-run",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["dry_run"] is True
    assert payload["will_call_provider"] is False
    assert payload["safety_flags"]["will_create_tasks"] is False
    assert payload["safety_flags"]["will_apply_patch"] is False
    assert not (tmp_path / ".devflow/reports/agent-advisory-runs").exists()


def test_agent_advise_writes_repo_scoped_openrouter_evidence_without_logging_secret(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test-secret")
    captured_requests: list[dict[str, Any]] = []

    def mock_urlopen(req: urllib.request.Request, timeout: float | None = None) -> MockResponse:
        captured_requests.append(
            {
                "url": req.full_url,
                "timeout": timeout,
                "payload": json.loads(req.data.decode("utf-8")),
            }
        )
        return MockResponse(
            {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "summary": "One stale context risk remains.",
                                    "recommendations": [
                                        {
                                            "title": "Create a focused cleanup task",
                                            "rationale": "The bounded packet points at stale direction risk.",
                                            "next_safe_action": 'devflow task create "Clean stale DeepSeek docs"',
                                        }
                                    ],
                                    "highest_impact_next_safe_action": 'devflow task create "Clean stale DeepSeek docs"',
                                }
                            )
                        }
                    }
                ],
                "usage": {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18},
            }
        )

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)

    result = runner.invoke(
        app,
        [
            "agent",
            "advise",
            "--profile",
            ADVISORY_PROFILE_ID,
            "--job",
            "gap-analysis",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "success"
    assert payload["provider"] == "openrouter"
    assert payload["model"] == ADVISORY_MODEL
    assert payload["usage"]["total_tokens"] == 18
    assert payload["recommendations"][0]["next_safe_action"].startswith("devflow task create")
    assert payload["safety_flags"]["will_run_workers"] is False
    assert payload["safety_flags"]["will_commit"] is False

    assert captured_requests[0]["url"] == "https://openrouter.ai/api/v1/chat/completions"
    assert captured_requests[0]["payload"]["model"] == ADVISORY_MODEL

    evidence_dir = tmp_path / payload["evidence_dir"]
    assert evidence_dir.is_dir()
    for key in ("prompt_path", "response_path", "run_metadata_path"):
        assert (tmp_path / payload[key]).exists()
    for evidence_file in evidence_dir.iterdir():
        if evidence_file.is_file():
            assert "sk-or-test-secret" not in evidence_file.read_text(encoding="utf-8")


def test_agent_advise_local_qwen35_automatically_ensures_managed_server(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    assert runner.invoke(app, ["task", "create", "qwen server lifecycle"]).exit_code == 0
    captured_lifecycle: list[dict[str, Any]] = []
    captured_requests: list[dict[str, Any]] = []

    from devflow.control_room import openrouter_agent

    def fake_ensure(**kwargs: Any) -> dict[str, Any]:
        captured_lifecycle.append(kwargs)
        return {
            "status": "already_running",
            "will_manage_local_server": True,
            "profile": "qwen35-mtp",
            "pid": 24842,
        }

    def mock_urlopen(req: urllib.request.Request, timeout: float | None = None) -> MockResponse:
        captured_requests.append(
            {
                "url": req.full_url,
                "payload": json.loads(req.data.decode("utf-8")),
            }
        )
        return MockResponse(
            {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "summary": "Qwen advisory evidence.",
                                    "recommendations": [
                                        {
                                            "title": "Review evidence",
                                            "rationale": "The run is advisory only.",
                                            "next_safe_action": "devflow task show task-0001",
                                        }
                                    ],
                                    "highest_impact_next_safe_action": "devflow task show task-0001",
                                }
                            )
                        }
                    }
                ]
            }
        )

    monkeypatch.setattr(openrouter_agent, "ensure_local_model_server_for_profile", fake_ensure)
    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)

    result = runner.invoke(
        app,
        [
            "agent",
            "advise",
            "--profile",
            "local-qwen35-mtp",
            "--task",
            "task-0001",
            "--job",
            "status",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert captured_lifecycle
    assert captured_lifecycle[0]["provider"] == "qwen35-mtp"
    assert captured_lifecycle[0]["model"] == "qwen35-9b-mtp"
    assert captured_lifecycle[0]["base_url"] == "http://127.0.0.1:8080/v1"
    assert captured_requests[0]["url"] == "http://127.0.0.1:8080/v1/chat/completions"
    assert payload["local_model_server_lifecycle"]["status"] == "already_running"
    run_metadata = json.loads((tmp_path / payload["run_metadata_path"]).read_text(encoding="utf-8"))
    assert run_metadata["local_model_server_lifecycle"]["profile"] == "qwen35-mtp"


def test_task_scoped_agent_advise_missing_key_fails_safely_without_provider_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    assert runner.invoke(app, ["task", "create", "task advice"]).exit_code == 0

    def fail_urlopen(req: urllib.request.Request, timeout: float | None = None) -> MockResponse:
        raise AssertionError("missing API key must fail before provider call")

    monkeypatch.setattr(urllib.request, "urlopen", fail_urlopen)

    result = runner.invoke(
        app,
        [
            "agent",
            "advise",
            "--profile",
            REVIEW_PROFILE_ID,
            "--task",
            "task-0001",
            "--job",
            "review",
            "--json",
        ],
    )

    assert result.exit_code != 0
    payload = json.loads(result.output)
    assert payload["status"] == "failed"
    assert "OPENROUTER_API_KEY" in payload["error"]
    assert payload["will_call_provider"] is False
    assert payload["evidence_dir"].startswith(".devflow/tasks/task-0001/agent-advisory-runs/")
    assert "sk-or" not in (tmp_path / payload["run_metadata_path"]).read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("profile_id", "model"),
    [
        (PATCH_PROFILE_ID, PATCH_MODEL),
    ],
)
def test_agent_propose_patch_writes_only_patch_proposal_evidence_and_keeps_gates_required(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    profile_id: str,
    model: str,
) -> None:
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-patch-secret")
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir(exist_ok=True)
    (docs_dir / "example.md").write_text("old\n", encoding="utf-8")
    subprocess.run(["git", "add", "docs/example.md"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "add docs example"], cwd=tmp_path, check=True)
    assert runner.invoke(app, ["task", "create", "patch proposal"]).exit_code == 0
    _write_test_patch_surface_profile(tmp_path)
    diff = """diff --git a/docs/example.md b/docs/example.md
--- a/docs/example.md
+++ b/docs/example.md
@@ -1 +1 @@
-old
+new
"""
    captured_requests: list[dict[str, Any]] = []

    def mock_urlopen(req: urllib.request.Request, timeout: float | None = None) -> MockResponse:
        captured_requests.append(
            {
                "timeout": timeout,
                "payload": json.loads(req.data.decode("utf-8")),
            }
        )
        return MockResponse(
            {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "status": "ready",
                                    "diff": diff,
                                    "summary": "Proposed a focused docs patch.",
                                }
                            )
                        }
                    }
                ]
            }
        )

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)

    result = runner.invoke(
        app,
        [
            "agent",
            "propose-patch",
            "--task",
            "task-0001",
            "--profile",
            profile_id,
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "success"
    assert captured_requests[0]["timeout"] == 90
    assert captured_requests[0]["payload"]["model"] == model
    assert captured_requests[0]["payload"]["max_tokens"] == 2048
    assert captured_requests[0]["payload"]["reasoning"] == {"effort": "minimal", "exclude": True}
    agent_dir = tmp_path / f".devflow/tasks/task-0001/agents/{profile_id}"
    assert sorted(path.name for path in agent_dir.iterdir()) == [
        "proposal.patch",
        "raw_output.md",
        "result.md",
        "run.json",
    ]
    assert (agent_dir / "proposal.patch").read_text(encoding="utf-8") == diff
    assert "sk-or-patch-secret" not in (agent_dir / "run.json").read_text(encoding="utf-8")

    apply_result = runner.invoke(
        app,
        ["task", "apply-patch", "task-0001", "--agent", profile_id],
    )
    assert apply_result.exit_code != 0
    assert "review-patch" in apply_result.output or "dry-run" in apply_result.output

    review_result = runner.invoke(
        app,
        ["task", "review-patch", "task-0001", "--agent", profile_id],
    )
    assert review_result.exit_code == 0, review_result.output


def test_agent_propose_patch_normalizes_malformed_hunk_counts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-patch-secret")
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir(exist_ok=True)
    (docs_dir / "example.md").write_text("old\n", encoding="utf-8")
    subprocess.run(["git", "add", "docs/example.md"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "add docs example"], cwd=tmp_path, check=True)
    assert runner.invoke(app, ["task", "create", "patch proposal"]).exit_code == 0
    _write_test_patch_surface_profile(tmp_path)
    malformed_diff = """diff --git a/docs/example.md b/docs/example.md
--- a/docs/example.md
+++ b/docs/example.md
@@ -1 +1 @@
-old
+new
+extra
"""
    responses = [
        {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "status": "ready",
                                "diff": malformed_diff,
                                "summary": "First attempt has malformed hunk counts.",
                            }
                        )
                    }
                }
            ]
        },
    ]
    prompts: list[str] = []

    def mock_urlopen(req: urllib.request.Request, timeout: float | None = None) -> MockResponse:
        prompts.append(json.loads(req.data.decode("utf-8"))["messages"][1]["content"])
        return MockResponse(responses.pop(0))

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)

    result = runner.invoke(
        app,
        [
            "agent",
            "propose-patch",
            "--task",
            "task-0001",
            "--profile",
            PATCH_PROFILE_ID,
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    assert len(prompts) == 1
    agent_dir = tmp_path / ".devflow/tasks/task-0001/agents" / PATCH_PROFILE_ID
    assert (agent_dir / "proposal.patch").read_text(encoding="utf-8") == normalize_hunk_line_counts(malformed_diff)
    raw_output = (agent_dir / "raw_output.md").read_text(encoding="utf-8")
    assert "First attempt has malformed hunk counts" in raw_output
    assert "@@ -1 +1 @@" in raw_output
    assert "@@ -1 +1,2 @@" not in raw_output


def test_agent_propose_patch_retries_patch_that_does_not_apply_to_workspace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-patch-secret")
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir(exist_ok=True)
    (docs_dir / "example.md").write_text("old\n", encoding="utf-8")
    subprocess.run(["git", "add", "docs/example.md"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "add docs example"], cwd=tmp_path, check=True)
    assert runner.invoke(app, ["task", "create", "patch proposal"]).exit_code == 0
    _write_test_patch_surface_profile(tmp_path)
    wrong_context_diff = """diff --git a/docs/example.md b/docs/example.md
--- a/docs/example.md
+++ b/docs/example.md
@@ -1 +1 @@
-different
+new
"""
    corrected_diff = """diff --git a/docs/example.md b/docs/example.md
--- a/docs/example.md
+++ b/docs/example.md
@@ -1 +1 @@
-old
+new
"""
    responses = [
        {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "status": "ready",
                                "diff": wrong_context_diff,
                                "summary": "First attempt has wrong context.",
                            }
                        )
                    }
                }
            ]
        },
        {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "status": "ready",
                                "diff": corrected_diff,
                                "summary": "Corrected workspace context.",
                            }
                        )
                    }
                }
            ]
        },
    ]
    prompts: list[str] = []

    def mock_urlopen(req: urllib.request.Request, timeout: float | None = None) -> MockResponse:
        prompts.append(json.loads(req.data.decode("utf-8"))["messages"][1]["content"])
        return MockResponse(responses.pop(0))

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)

    result = runner.invoke(
        app,
        [
            "agent",
            "propose-patch",
            "--task",
            "task-0001",
            "--profile",
            PATCH_PROFILE_ID,
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    assert len(prompts) == 2
    assert "Previous Patch Proposal Was Rejected" in prompts[1]
    assert "original context did not match" in prompts[1]
    agent_dir = tmp_path / ".devflow/tasks/task-0001/agents" / PATCH_PROFILE_ID
    assert (agent_dir / "proposal.patch").read_text(encoding="utf-8") == corrected_diff
    raw_output = (agent_dir / "raw_output.md").read_text(encoding="utf-8")
    assert "## Attempt 1" in raw_output
    assert "## Attempt 2" in raw_output
    assert "First attempt has wrong context" in raw_output
    assert "Corrected workspace context" in raw_output


def test_agent_propose_patch_prompt_includes_referenced_worker_context(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup_temp_git_repo(tmp_path)
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir(exist_ok=True)
    (docs_dir / "example.md").write_text("# Operator Notes\n\nOriginal operator docs.\n", encoding="utf-8")
    subprocess.run(["git", "add", "docs/example.md"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "add docs example"], cwd=tmp_path, check=True)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-patch-secret")
    assert runner.invoke(app, ["task", "create", "patch docs/example.md documentation"]).exit_code == 0
    _write_test_patch_surface_profile(tmp_path)

    captured_requests: list[dict[str, Any]] = []

    def mock_urlopen(req: urllib.request.Request, timeout: float | None = None) -> MockResponse:
        body = json.loads(req.data.decode("utf-8"))
        captured_requests.append(body)
        return MockResponse(
            {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "status": "ready",
                                    "diff": """diff --git a/docs/example.md b/docs/example.md
--- a/docs/example.md
+++ b/docs/example.md
@@ -3 +3 @@
-Original operator docs.
+Updated operator docs.
""",
                                    "summary": "Proposed a focused docs patch.",
                                }
                            )
                        }
                    }
                ]
            }
        )

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)

    result = runner.invoke(
        app,
        [
            "agent",
            "propose-patch",
            "--task",
            "task-0001",
            "--profile",
            PATCH_PROFILE_ID,
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    assert captured_requests
    prompt = captured_requests[0]["messages"][1]["content"]
    assert "## Bounded Worker Context Sources" in prompt
    assert "docs/example.md" in prompt
    assert "Original operator docs." in prompt


def test_agent_propose_patch_minimal_prompt_uses_explicit_file_context_without_packets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup_temp_git_repo(tmp_path)
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir(exist_ok=True)
    (docs_dir / "example.md").write_text("# Tiny Example\n\nOriginal tiny docs.\n", encoding="utf-8")
    subprocess.run(["git", "add", "docs/example.md"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "add docs example"], cwd=tmp_path, check=True)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-patch-secret")
    monkeypatch.setenv("DEVFLOW_OPENROUTER_PATCH_PROMPT_MODE", "minimal")
    assert (
        runner.invoke(
            app,
            ["task", "create", "Update docs/example.md tiny wording. Verify with git diff --check"],
        ).exit_code
        == 0
    )
    _write_test_patch_surface_profile(tmp_path)
    task_yaml = tmp_path / ".devflow/tasks/task-0001/task.yaml"
    task_yaml.write_text(
        task_yaml.read_text(encoding="utf-8")
        + "description: Keep docs/example.md clear without broad context.\n",
        encoding="utf-8",
    )

    def fail_build_agent_packet(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("minimal prompt must not build a TaskPacket")

    monkeypatch.setattr("devflow.control_room.openrouter_agent.build_agent_packet", fail_build_agent_packet)

    captured_requests: list[dict[str, Any]] = []

    def mock_urlopen(req: urllib.request.Request, timeout: float | None = None) -> MockResponse:
        body = json.loads(req.data.decode("utf-8"))
        captured_requests.append(body)
        return MockResponse(
            {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "status": "ready",
                                    "diff": """diff --git a/docs/example.md b/docs/example.md
--- a/docs/example.md
+++ b/docs/example.md
@@ -3 +3 @@
-Original tiny docs.
+Updated tiny docs.
""",
                                    "summary": "Proposed a focused docs patch.",
                                }
                            )
                        }
                    }
                ]
            }
        )

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)

    result = runner.invoke(
        app,
        [
            "agent",
            "propose-patch",
            "--task",
            "task-0001",
            "--profile",
            PATCH_PROFILE_ID,
            "--max-prompt-chars",
            "6000",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    prompt = captured_requests[0]["messages"][1]["content"]
    assert payload["prompt_mode"] == "minimal"
    assert payload["prompt_chars"] == len(prompt)
    assert captured_requests[0]["reasoning"] == {"enabled": False, "exclude": True}
    assert "docs/example.md" in prompt
    assert "Original tiny docs." in prompt
    assert '"status"' in prompt
    assert '"diff"' in prompt
    assert '"summary"' in prompt
    assert "Verify with git diff --check" in prompt
    assert "## Bounded Task Packet" not in prompt
    assert "## Bounded Worker Context Sources" not in prompt
    assert "allowed_artifacts" not in prompt
    assert "events.jsonl" not in prompt
    assert "task_created" not in prompt

    agent_dir = tmp_path / ".devflow/tasks/task-0001/agents" / PATCH_PROFILE_ID
    assert (agent_dir / "proposal.patch").exists()
    run_payload = json.loads((agent_dir / "run.json").read_text(encoding="utf-8"))
    assert run_payload["prompt_mode"] == "minimal"
    assert run_payload["prompt_chars"] == len(prompt)


def test_agent_propose_patch_invalid_prompt_mode_fails_before_openrouter(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-patch-secret")
    monkeypatch.setenv("DEVFLOW_OPENROUTER_PATCH_PROMPT_MODE", "bulky")
    assert runner.invoke(app, ["task", "create", "patch docs/example.md"]).exit_code == 0
    _write_test_patch_surface_profile(tmp_path)

    def fail_urlopen(req: urllib.request.Request, timeout: float | None = None) -> MockResponse:
        raise AssertionError("invalid prompt mode must fail before OpenRouter")

    monkeypatch.setattr(urllib.request, "urlopen", fail_urlopen)

    result = runner.invoke(
        app,
        [
            "agent",
            "propose-patch",
            "--task",
            "task-0001",
            "--profile",
            PATCH_PROFILE_ID,
            "--json",
        ],
    )

    assert result.exit_code != 0
    assert "DEVFLOW_OPENROUTER_PATCH_PROMPT_MODE" in result.output
    assert not (tmp_path / ".devflow/tasks/task-0001/agents" / PATCH_PROFILE_ID / "run.json").exists()
