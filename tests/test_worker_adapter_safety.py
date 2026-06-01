from __future__ import annotations

import os
from pathlib import Path
import pytest

from devflow.control_room.worker_adapter import UnsupportedWorkerAdapter, get_worker_adapter
from devflow.control_room.models import WorkerInput
from devflow.control_room.openai_compatible_worker import OpenAICompatibleWorkerAdapter
from devflow.control_room.anthropic_worker import AnthropicMessagesWorkerAdapter
from devflow.control_room.gemini_worker import GeminiWorkerAdapter
from devflow.control_room.openai_chat_worker import OpenAIChatWorkerAdapter
from devflow.control_room.agent_registry import load_agent_registry, load_provider_registry, is_local_patch_runtime_agent


def test_remote_adapters_cannot_execute_by_default() -> None:
    # Standard CLI get_worker_adapter rejects non-stable runtime adapters when agent is None
    for name in ["openai_compatible", "anthropic_messages", "gemini", "openai_chat"]:
        with pytest.raises(UnsupportedWorkerAdapter, match="planned_not_executable|experimental_readonly"):
            get_worker_adapter(name)


def test_openai_compatible_fails_closed_when_key_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    
    task_dir = tmp_path / ".devflow" / "tasks" / "task-openai-fail"
    task_dir.mkdir(parents=True)
    (task_dir / "logs").mkdir(parents=True)
    (task_dir / "task.yaml").write_text("id: task-openai-fail\ntitle: Test\nstatus: created\n", encoding="utf-8")
    
    workspace_path = tmp_path / ".devflow" / "workspaces" / "task-openai-fail"
    workspace_path.mkdir(parents=True)
    
    log_file = task_dir / "logs" / "worker.log"
    result_file = task_dir / "result.md"
    
    worker_input = WorkerInput(
        task_id="task-openai-fail",
        repo_root=tmp_path,
        workspace_path=workspace_path,
        task_file=task_dir / "task.yaml",
        context_file=task_dir / "events.jsonl",
        status_file=task_dir / "task.yaml",
        questions_file=task_dir / "questions.jsonl",
        result_file=result_file,
        log_file=log_file,
        command=["openai_compatible", "task"],
        timeout_seconds=60,
    )
    
    adapter = OpenAICompatibleWorkerAdapter()
    result = adapter.run(worker_input)
    
    assert result.status == "worker_failed"
    assert result.exit_code == 1
    assert "OpenAI-compatible provider API key is not configured" in result.summary
    assert "mock-key" not in result.summary


def test_anthropic_fails_closed_when_key_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    
    task_dir = tmp_path / ".devflow" / "tasks" / "task-anthropic-fail"
    task_dir.mkdir(parents=True)
    (task_dir / "logs").mkdir(parents=True)
    (task_dir / "task.yaml").write_text("id: task-anthropic-fail\ntitle: Test\nstatus: created\n", encoding="utf-8")
    
    workspace_path = tmp_path / ".devflow" / "workspaces" / "task-anthropic-fail"
    workspace_path.mkdir(parents=True)
    
    log_file = task_dir / "logs" / "worker.log"
    result_file = task_dir / "result.md"
    
    worker_input = WorkerInput(
        task_id="task-anthropic-fail",
        repo_root=tmp_path,
        workspace_path=workspace_path,
        task_file=task_dir / "task.yaml",
        context_file=task_dir / "events.jsonl",
        status_file=task_dir / "task.yaml",
        questions_file=task_dir / "questions.jsonl",
        result_file=result_file,
        log_file=log_file,
        command=["anthropic_messages", "task"],
        timeout_seconds=60,
    )
    
    adapter = AnthropicMessagesWorkerAdapter()
    result = adapter.run(worker_input)
    
    assert result.status == "worker_failed"
    assert result.exit_code == 1
    assert "Anthropic provider API key is not configured" in result.summary
    assert "mock-key" not in result.summary


def test_gemini_fails_closed_when_key_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    
    task_dir = tmp_path / ".devflow" / "tasks" / "task-gemini-fail"
    task_dir.mkdir(parents=True)
    (task_dir / "logs").mkdir(parents=True)
    (task_dir / "task.yaml").write_text("id: task-gemini-fail\ntitle: Test\nstatus: created\n", encoding="utf-8")
    
    workspace_path = tmp_path / ".devflow" / "workspaces" / "task-gemini-fail"
    workspace_path.mkdir(parents=True)
    
    log_file = task_dir / "logs" / "worker.log"
    result_file = task_dir / "result.md"
    
    worker_input = WorkerInput(
        task_id="task-gemini-fail",
        repo_root=tmp_path,
        workspace_path=workspace_path,
        task_file=task_dir / "task.yaml",
        context_file=task_dir / "events.jsonl",
        status_file=task_dir / "task.yaml",
        questions_file=task_dir / "questions.jsonl",
        result_file=result_file,
        log_file=log_file,
        command=["gemini", "task"],
        timeout_seconds=60,
    )
    
    adapter = GeminiWorkerAdapter()
    result = adapter.run(worker_input)
    
    assert result.status == "worker_failed"
    assert result.exit_code == 1
    assert "Gemini provider API key is not configured" in result.summary
    assert "mock-key" not in result.summary


def test_openai_chat_fails_closed_when_key_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    
    task_dir = tmp_path / ".devflow" / "tasks" / "task-openaichat-fail"
    task_dir.mkdir(parents=True)
    (task_dir / "logs").mkdir(parents=True)
    (task_dir / "task.yaml").write_text("id: task-openaichat-fail\ntitle: Test\nstatus: created\n", encoding="utf-8")
    
    workspace_path = tmp_path / ".devflow" / "workspaces" / "task-openaichat-fail"
    workspace_path.mkdir(parents=True)
    
    log_file = task_dir / "logs" / "worker.log"
    result_file = task_dir / "result.md"
    
    worker_input = WorkerInput(
        task_id="task-openaichat-fail",
        repo_root=tmp_path,
        workspace_path=workspace_path,
        task_file=task_dir / "task.yaml",
        context_file=task_dir / "events.jsonl",
        status_file=task_dir / "task.yaml",
        questions_file=task_dir / "questions.jsonl",
        result_file=result_file,
        log_file=log_file,
        command=["openai_chat", "task"],
        timeout_seconds=60,
    )
    
    adapter = OpenAIChatWorkerAdapter()
    result = adapter.run(worker_input)
    
    assert result.status == "worker_failed"
    assert result.exit_code == 1
    assert "OpenAI Chat provider API key is not configured" in result.summary
    assert "mock-key" not in result.summary


def test_custom_api_key_env_fails_closed_when_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # If agent profile specifies a custom api_key_env that is unset, it must fail closed
    task_dir = tmp_path / ".devflow" / "tasks" / "task-custom-fail"
    task_dir.mkdir(parents=True)
    (task_dir / "logs").mkdir(parents=True)
    (task_dir / "task.yaml").write_text("id: task-custom-fail\ntitle: Test\nstatus: created\n", encoding="utf-8")
    
    # Configure custom agent/provider registry via files in .devflow
    agents_dir = tmp_path / ".devflow" / "agents"
    agents_dir.mkdir(parents=True)
    (agents_dir / "registry.yaml").write_text(
        "version: 1\n"
        "agents:\n"
        "  custom-agent:\n"
        "    provider: custom-prov\n"
        "    model: custom-model\n"
        "    adapter: openai_compatible\n"
        "    role: implementation_worker\n"
        "    tier: strong_local\n"
        "    default_mode: workspace_write\n"
        "    workspace: isolated_task_workspace\n"
        "    enabled: true\n",
        encoding="utf-8"
    )
    
    providers_dir = tmp_path / ".devflow" / "providers"
    providers_dir.mkdir(parents=True)
    (providers_dir / "custom-prov.yaml").write_text(
        "provider: custom-prov\n"
        "adapter: openai_compatible\n"
        "api_key_env: CUSTOM_SECRET_KEY\n"
        "enabled: true\n",
        encoding="utf-8"
    )
    
    workspace_path = tmp_path / ".devflow" / "workspaces" / "task-custom-fail"
    workspace_path.mkdir(parents=True)
    
    log_file = task_dir / "logs" / "worker.log"
    result_file = task_dir / "result.md"
    
    worker_input = WorkerInput(
        task_id="task-custom-fail",
        repo_root=tmp_path,
        workspace_path=workspace_path,
        task_file=task_dir / "task.yaml",
        context_file=task_dir / "events.jsonl",
        status_file=task_dir / "task.yaml",
        questions_file=task_dir / "questions.jsonl",
        result_file=result_file,
        log_file=log_file,
        command=["openai_compatible", "task"],
        env={"DEVFLOW_AGENT_ID": "custom-agent"},
        timeout_seconds=60,
    )
    
    monkeypatch.delenv("CUSTOM_SECRET_KEY", raising=False)
    
    adapter = OpenAICompatibleWorkerAdapter()
    result = adapter.run(worker_input)
    
    assert result.status == "worker_failed"
    assert result.exit_code == 1
    assert "Provider 'custom-prov' requires api_key_env 'CUSTOM_SECRET_KEY', but that environment variable is not set." in result.summary
    assert "mock-key" not in result.summary


def test_ollama_base_url_only_permits_loopback_hosts() -> None:
    from devflow.control_room.agent_registry import is_local_ollama_base_url
    # Valid loopback hosts
    assert is_local_ollama_base_url("http://127.0.0.1:11434") is True
    assert is_local_ollama_base_url("http://localhost:11434") is True
    assert is_local_ollama_base_url("http://[::1]:11434") is True
    assert is_local_ollama_base_url(None) is True
    assert is_local_ollama_base_url("") is True

    # Invalid external hosts
    assert is_local_ollama_base_url("http://ollama-server.local:11434") is False
    assert is_local_ollama_base_url("http://192.168.1.50:11434") is False
    assert is_local_ollama_base_url("https://external-ollama.io") is False
