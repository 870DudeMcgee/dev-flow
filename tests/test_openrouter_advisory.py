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


class MockResponse:
    def __init__(self, body: dict[str, Any]) -> None:
        self.body = json.dumps(body).encode("utf-8")

    def read(self, *args: Any, **kwargs: Any) -> bytes:
        return self.body

    def __enter__(self) -> "MockResponse":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        return None


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
            "deepseek-v4-flash-planner",
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
            "deepseek-v4-flash-planner",
            "--job",
            "gap-analysis",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "success"
    assert payload["provider"] == "openrouter"
    assert payload["model"] == "deepseek/deepseek-v4-flash"
    assert payload["usage"]["total_tokens"] == 18
    assert payload["recommendations"][0]["next_safe_action"].startswith("devflow task create")
    assert payload["safety_flags"]["will_run_workers"] is False
    assert payload["safety_flags"]["will_commit"] is False

    assert captured_requests[0]["url"] == "https://openrouter.ai/api/v1/chat/completions"
    assert captured_requests[0]["payload"]["model"] == "deepseek/deepseek-v4-flash"

    evidence_dir = tmp_path / payload["evidence_dir"]
    assert evidence_dir.is_dir()
    for key in ("prompt_path", "response_path", "run_metadata_path"):
        assert (tmp_path / payload[key]).exists()
    for evidence_file in evidence_dir.iterdir():
        if evidence_file.is_file():
            assert "sk-or-test-secret" not in evidence_file.read_text(encoding="utf-8")


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
            "deepseek-v4-pro-reviewer",
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
        ("deepseek-v4-pro-patch-proposer", "deepseek/deepseek-v4-pro"),
        ("deepseek-v4-flash-patch-proposer", "deepseek/deepseek-v4-flash"),
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
            "deepseek-v4-pro-patch-proposer",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    assert len(prompts) == 1
    agent_dir = tmp_path / ".devflow/tasks/task-0001/agents/deepseek-v4-pro-patch-proposer"
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
            "deepseek-v4-pro-patch-proposer",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    assert len(prompts) == 2
    assert "Previous Patch Proposal Was Rejected" in prompts[1]
    assert "original context did not match" in prompts[1]
    agent_dir = tmp_path / ".devflow/tasks/task-0001/agents/deepseek-v4-pro-patch-proposer"
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

    captured_prompts: list[str] = []

    def mock_urlopen(req: urllib.request.Request, timeout: float | None = None) -> MockResponse:
        body = json.loads(req.data.decode("utf-8"))
        captured_prompts.append(body["messages"][1]["content"])
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
            "deepseek-v4-pro-patch-proposer",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    assert captured_prompts
    assert "## Bounded Worker Context Sources" in captured_prompts[0]
    assert "docs/example.md" in captured_prompts[0]
    assert "Original operator docs." in captured_prompts[0]
