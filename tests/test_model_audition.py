from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from typer.testing import CliRunner

from devflow.cli import app
from devflow.control_room.local_agent_discovery import LocalDiscoveryReport, parse_ollama_list
from devflow.control_room.service import create_task
from tests.helpers import setup_temp_git_repo


runner = CliRunner()


OLLAMA_LIST_REVIEW = """NAME                              ID              SIZE      MODIFIED
gemma4:12b-it-qat                 bbb222          8.1 GB    1 day ago
qwen2.5-coder:14b                 ccc333          9.0 GB    1 day ago
"""


OLLAMA_LIST_UNSAFE = """NAME                              ID              SIZE      MODIFIED
qwen2.5-coder:14b                 ccc333          9.0 GB    1 day ago
"""


OLLAMA_SHOWS = {
    "gemma4:12b-it-qat": """  Model
    architecture        gemma4
    parameters          11.9B
    context length      262144
    quantization        Q4_0

  Capabilities
    completion
    thinking
    vision
""",
    "qwen2.5-coder:14b": """  Model
    architecture        qwen2
    parameters          14B
    context length      32768
    quantization        Q4_K_M

  Capabilities
    completion
""",
}


def test_agent_audition_dry_run_writes_plan_without_model_calls(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    create_result = runner.invoke(app, ["task", "create", "debug flaky local worker evidence"])
    assert create_result.exit_code == 0, create_result.output
    monkeypatch.setattr(subprocess, "run", _fake_ollama_run(OLLAMA_LIST_REVIEW))

    result = runner.invoke(
        app,
        ["agent", "audition", "task-0001", "--job", "review-debug", "--dry-run", "--json"],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["dry_run"] is True
    assert payload["will_call_models"] is False
    assert payload["will_write_source"] is False
    assert payload["will_write_proposal_patch"] is False
    assert payload["will_commit_merge_push_or_promote"] is False
    assert payload["job_type"] == "review-debug"
    assert payload["candidate_cap"] == 3
    assert [item["profile_id"] for item in payload["selected_candidates"]] == [
        "local-gemma4-qat",
        "local-qwen25-coder-14b",
    ]
    assert len(payload["selected_candidates"]) <= 3

    plan_path = tmp_path / payload["plan_path"]
    assert plan_path.exists()
    saved = json.loads(plan_path.read_text(encoding="utf-8"))
    assert saved["audition_id"] == payload["audition_id"]
    assert saved["selected_candidates"] == payload["selected_candidates"]
    assert not (plan_path.parent / "runs.json").exists()
    assert not (tmp_path / ".devflow/tasks/task-0001/local-model-runs").exists()


def test_agent_audition_unknown_job_lists_valid_job_types(tmp_path: Path, monkeypatch: Any) -> None:
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    create_task(tmp_path, "unknown audition job")

    result = runner.invoke(
        app,
        ["agent", "audition", "task-0001", "--job", "space-whales", "--dry-run", "--json"],
    )

    assert result.exit_code == 1
    assert "Unknown job type 'space-whales'" in result.output
    assert "planning" in result.output
    assert "review-debug" in result.output


def test_agent_audition_rejects_patch_capable_profile(tmp_path: Path, monkeypatch: Any) -> None:
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    create_task(tmp_path, "unsafe local audition")
    _write_unsafe_fast_reviewer(tmp_path)
    monkeypatch.setattr(subprocess, "run", _fake_ollama_run(OLLAMA_LIST_UNSAFE))

    result = runner.invoke(
        app,
        ["agent", "audition", "task-0001", "--job", "review-debug", "--dry-run", "--json"],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    rejected = {
        item["profile_id"]: item["reasons"]
        for item in payload["rejected_candidates"]
        if item.get("profile_id")
    }
    assert "unsafe_profile" in rejected["local-qwen25-coder-14b"]
    assert payload["selected_candidates"] == []
    assert payload["status"] == "no_eligible_candidates"


def test_agent_audition_execute_runs_candidates_and_writes_score_artifacts(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    create_task(tmp_path, "execute reserved")
    _commit_all(tmp_path, "task baseline")
    monkeypatch.setattr(
        "devflow.control_room.model_audition.discover_local_ollama_models",
        lambda: LocalDiscoveryReport(parse_ollama_list(OLLAMA_LIST_REVIEW), [], []),
    )
    calls: list[str] = []

    def fake_run_local_model_profile(**kwargs: Any) -> dict[str, Any]:
        profile_id = kwargs["profile_id"]
        calls.append(profile_id)
        run_id = f"run-{profile_id}"
        evidence_dir = tmp_path / ".devflow" / "tasks" / kwargs["task_id"] / "local-model-runs" / run_id
        evidence_dir.mkdir(parents=True, exist_ok=True)
        response_text = _audition_response(profile_id)
        (evidence_dir / "response.md").write_text(response_text, encoding="utf-8")
        (evidence_dir / "run.json").write_text(
            json.dumps(
                {
                    "task_id": kwargs["task_id"],
                    "profile_id": profile_id,
                    "worker_id": profile_id,
                    "run_id": run_id,
                    "status": "success",
                    "model": profile_id,
                    "adapter": "ollama_chat",
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        return {
            "task_id": kwargs["task_id"],
            "profile_id": profile_id,
            "worker_id": profile_id,
            "status": "success",
            "run_id": run_id,
            "model": profile_id,
            "adapter": "ollama_chat",
            "evidence_dir": f".devflow/tasks/{kwargs['task_id']}/local-model-runs/{run_id}",
            "run_metadata_path": f".devflow/tasks/{kwargs['task_id']}/local-model-runs/{run_id}/run.json",
            "response_path": f".devflow/tasks/{kwargs['task_id']}/local-model-runs/{run_id}/response.md",
        }

    monkeypatch.setattr(
        "devflow.control_room.model_audition.run_local_model_profile",
        fake_run_local_model_profile,
    )

    result = runner.invoke(
        app,
        ["agent", "audition", "task-0001", "--job", "review-debug", "--execute", "--json"],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["dry_run"] is False
    assert payload["status"] == "completed"
    assert payload["will_call_models"] is True
    assert calls == [
        "local-gemma4-qat",
        "local-qwen25-coder-14b",
    ]
    audition_dir = tmp_path / ".devflow/tasks/task-0001/model-auditions/execute-review-debug"
    assert (audition_dir / "plan.json").exists()
    assert (audition_dir / "runs.json").exists()
    assert (audition_dir / "scorecard.json").exists()
    assert (audition_dir / "report.md").exists()
    runs = json.loads((audition_dir / "runs.json").read_text(encoding="utf-8"))
    scorecard = json.loads((audition_dir / "scorecard.json").read_text(encoding="utf-8"))
    assert len(runs["runs"]) == 2
    assert scorecard["advisory_ranking"][0]["profile_id"] == "local-gemma4-qat"
    assert scorecard["advisory_ranking"][0]["estimated_human_rework"] == "low"
    qwen_row = next(row for row in scorecard["advisory_ranking"] if row["profile_id"] == "local-qwen25-coder-14b")
    assert "false_claim" in qwen_row["deductions"]
    assert not (tmp_path / ".devflow/tasks/task-0001/task.yaml").read_text(encoding="utf-8").count("model_audition")


def test_agent_audition_execute_refuses_unsafe_git_state_before_model_calls(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    create_task(tmp_path, "unsafe execute")
    monkeypatch.setattr(
        "devflow.control_room.model_audition.discover_local_ollama_models",
        lambda: LocalDiscoveryReport(parse_ollama_list(OLLAMA_LIST_REVIEW), [], []),
    )
    calls: list[str] = []

    def fail_run_local_model_profile(**kwargs: Any) -> dict[str, Any]:
        calls.append(kwargs["profile_id"])
        raise AssertionError("unsafe execute must not call model workers")

    monkeypatch.setattr(
        "devflow.control_room.model_audition.run_local_model_profile",
        fail_run_local_model_profile,
    )

    result = runner.invoke(
        app,
        ["agent", "audition", "task-0001", "--job", "review-debug", "--execute", "--json"],
    )

    assert result.exit_code == 1
    assert "unsafe for worker writes" in result.output
    assert calls == []
    assert not (tmp_path / ".devflow/tasks/task-0001/local-model-runs").exists()


def _fake_ollama_run(list_output: str):
    calls: list[list[str]] = []

    def fake(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        if args == ["ollama", "list"]:
            return subprocess.CompletedProcess(args, 0, stdout=list_output, stderr="")
        if len(args) == 3 and args[:2] == ["ollama", "show"]:
            model = args[2]
            return subprocess.CompletedProcess(args, 0, stdout=OLLAMA_SHOWS.get(model, ""), stderr="")
        return subprocess.CompletedProcess(args, 1, stdout="", stderr=f"unexpected command: {args}")

    fake.calls = calls
    return fake


def _audition_response(profile_id: str) -> str:
    if profile_id == "local-gemma4-qat":
        return (
            "## Task Grounding\n"
            "- Task ID: task-0001\n"
            "- Task Title: execute reserved\n"
            "- Task Status: created\n\n"
            "## Summary\nPacket evidence is grounded.\n\n"
            "## Findings\n- The task needs review-debug audition evidence.\n\n"
            "## Risks Or Questions\n- No verification evidence is present.\n\n"
            "## Suggested Next Dev-Flow Action\n"
            "devflow task show task-0001\n"
        )
    if profile_id == "local-qwen25-coder-14b":
        return (
            "## Task Grounding\nTask ID: task-0001\n\n"
            "## Summary\nI edited files and ran verification successfully.\n\n"
            "## Suggested Next Dev-Flow Action\nPromote it.\n"
        )
    return "Generic response without task grounding."


def _commit_all(root: Path, message: str) -> None:
    subprocess.run(["git", "add", "."], cwd=root, capture_output=True, text=True, check=True)
    subprocess.run(["git", "commit", "-m", message], cwd=root, capture_output=True, text=True, check=True)


def _write_unsafe_fast_reviewer(root: Path) -> None:
    agents_dir = root / ".devflow" / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    (agents_dir / "registry.yaml").write_text(
        """version: 1
agents:
  local-qwen25-coder-14b:
    provider: ollama
    model: qwen2.5-coder:14b
    adapter: ollama_chat
    role: implementation_worker
    tier: fast_local
    default_mode: workspace_write
    execution_mode: automated
    workspace: isolated_task_workspace
    can_touch:
      - "<workspace>/**"
      - "<task>/agents/local-qwen25-coder-14b/proposal.patch"
    allowed_writes:
      - "<workspace>/**"
      - "<task>/agents/local-qwen25-coder-14b/proposal.patch"
    forbidden_writes:
      - "<main_checkout>/**"
      - ".git/**"
    can_run_shell: false
    can_use_network: false
    can_promote: false
    enabled: true
""",
        encoding="utf-8",
    )
