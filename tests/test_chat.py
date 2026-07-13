"""Tests for the DevFlow chat backend and server chat endpoints.

The chat surface is the brainstorm stage of the product-building loop. These
tests verify model listing, session lifecycle, transcript access, and message
dispatch — all without making real model calls (the model client is mocked).
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from devflow.control_room import chat as chat_api
from devflow.loop.pipeline_run import load_pipeline_run
from devflow.loop.registry import _reload_registry


@pytest.fixture
def repo_root(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture(autouse=True)
def ensure_registry():
    """Make sure the registry is loaded with the real models.yaml."""
    _reload_registry()
    yield


# ---------------------------------------------------------------------------
# Model listing
# ---------------------------------------------------------------------------

def test_list_chat_models_returns_eligible_models() -> None:
    """list_chat_models returns models with conversation-relevant capabilities."""
    models = chat_api.list_chat_models()
    assert len(models) > 0
    # All returned models should be eligible (available + not retired)
    for m in models:
        assert "name" in m
        assert "display_name" in m
        assert "transport" in m
        assert "cost_class" in m


def test_list_chat_models_excludes_unavailable() -> None:
    """Models marked available: false should not appear in chat models."""
    models = chat_api.list_chat_models()
    names = [m["name"] for m in models]
    # Mac Studio-only models are marked available: false
    assert "ornith-35b" not in names
    assert "qwen-27b-q5km" not in names


def test_list_chat_models_excludes_worker_only_laguna() -> None:
    """Worker-only models should not appear in brainstorm chat."""
    names = {model["name"] for model in chat_api.list_chat_models()}

    assert "laguna-m1-free" not in names


def test_list_chat_models_includes_available_local_reasoning_models() -> None:
    """The UI lists registry-eligible locals without an ad-hoc capability gate."""
    names = {model["name"] for model in chat_api.list_chat_models()}

    assert "qwythos-9b-v2-mini" in names
    assert "qwythos-9b-mini" not in names
    assert "ornith-9b-mini" in names


# ---------------------------------------------------------------------------
# Session management
# ---------------------------------------------------------------------------

def test_start_chat_session_creates_pipeline_run(repo_root: Path) -> None:
    """Starting a chat session creates a pipeline run at stage=idea."""
    with patch.object(chat_api, "_call_model", return_value=("Test response", {})):
        result = chat_api.start_chat_session(
            repo_root,
            intent="Build a todo app",
            model="glm-5.2",
        )
    assert result["session_id"]
    assert result["run_id"]
    assert result["model"] == "glm-5.2"
    assert result["response"]["content"] == "Test response"
    assert result["response"]["role"] == "assistant"


def test_start_chat_session_persists_transcript(repo_root: Path) -> None:
    """The first message and response are persisted to the transcript."""
    with patch.object(chat_api, "_call_model", return_value=("Hello!", {})):
        result = chat_api.start_chat_session(
            repo_root,
            intent="Test idea",
            model="glm-5.2",
        )
    transcript = chat_api.get_transcript(repo_root, result["session_id"])
    assert len(transcript) == 2
    assert transcript[0]["role"] == "user"
    assert transcript[0]["content"] == "Test idea"
    assert transcript[1]["role"] == "assistant"
    assert transcript[1]["content"] == "Hello!"
    assert transcript[1]["model"] == "glm-5.2"

    feed = load_pipeline_run(repo_root, result["run_id"])["worker-feed.jsonl"]
    assert [entry["event"] for entry in feed] == ["started", "completed"]
    assert all(entry["role"] == "brainstorm" for entry in feed)
    assert feed[-1]["content"] == "Hello!"


def test_session_model_persists(repo_root: Path) -> None:
    """The selected model is persisted and retrievable."""
    with patch.object(chat_api, "_call_model", return_value=("ok", {})):
        result = chat_api.start_chat_session(
            repo_root,
            intent="Test",
            model="gpt-5.6-terra",
        )
    saved = chat_api._get_session_model(repo_root, result["session_id"])
    assert saved == "gpt-5.6-terra"


def test_list_chat_sessions_returns_created_sessions(repo_root: Path) -> None:
    """list_chat_sessions returns sessions newest-first with previews."""
    with patch.object(chat_api, "_call_model", return_value=("r1", {})):
        r1 = chat_api.start_chat_session(repo_root, intent="First idea", model="glm-5.2")
    with patch.object(chat_api, "_call_model", return_value=("r2", {})):
        r2 = chat_api.start_chat_session(repo_root, intent="Second idea", model="glm-5.2")

    sessions = chat_api.list_chat_sessions(repo_root)
    assert len(sessions) >= 2
    # Newest first
    assert sessions[0]["session_id"] == r2["session_id"]
    assert sessions[1]["session_id"] == r1["session_id"]
    assert "First idea" in sessions[1]["preview"]


# ---------------------------------------------------------------------------
# Transcript access
# ---------------------------------------------------------------------------

def test_get_transcript_empty_for_nonexistent_session(repo_root: Path) -> None:
    """get_transcript returns [] for a session that doesn't exist."""
    transcript = chat_api.get_transcript(repo_root, "nonexistent-session")
    assert transcript == []


@pytest.mark.parametrize("session_id", ["../escape", "nested/../../escape"])
def test_session_paths_reject_traversal(repo_root: Path, session_id: str) -> None:
    """Transcript, link, and chat-model paths stay inside brainstorms."""
    with pytest.raises(ValueError, match="Invalid brainstorm session_id"):
        chat_api.get_transcript(repo_root, session_id)
    with pytest.raises(ValueError, match="Invalid brainstorm session_id"):
        chat_api._get_session_model(repo_root, session_id)
    with pytest.raises(ValueError, match="Invalid brainstorm session_id"):
        chat_api._set_session_model(repo_root, session_id, "glm-5.2")


def test_get_transcript_returns_all_messages(repo_root: Path) -> None:
    """get_transcript returns the full conversation history."""
    with patch.object(chat_api, "_call_model", return_value=("response1", {})):
        result = chat_api.start_chat_session(
            repo_root, intent="msg1", model="glm-5.2",
        )
    sid = result["session_id"]

    with patch.object(chat_api, "_call_model", return_value=("response2", {})):
        chat_api.send_message(repo_root, session_id=sid, message="msg2", model="glm-5.2")

    transcript = chat_api.get_transcript(repo_root, sid)
    assert len(transcript) == 4  # user, assistant, user, assistant
    assert transcript[0]["role"] == "user"
    assert transcript[0]["content"] == "msg1"
    assert transcript[1]["role"] == "assistant"
    assert transcript[1]["content"] == "response1"
    assert transcript[2]["role"] == "user"
    assert transcript[2]["content"] == "msg2"
    assert transcript[3]["role"] == "assistant"
    assert transcript[3]["content"] == "response2"


# ---------------------------------------------------------------------------
# Message dispatch
# ---------------------------------------------------------------------------

def test_send_message_appends_to_transcript(repo_root: Path) -> None:
    """send_message adds user + assistant messages and returns the response."""
    with patch.object(chat_api, "_call_model", return_value=("initial", {})):
        result = chat_api.start_chat_session(
            repo_root, intent="start", model="glm-5.2",
        )
    sid = result["session_id"]

    with patch.object(chat_api, "_call_model", return_value=("follow-up answer", {})):
        resp = chat_api.send_message(
            repo_root, session_id=sid, message="follow up", model="glm-5.2",
        )

    assert resp["content"] == "follow-up answer"
    assert resp["model"] == "glm-5.2"
    assert resp["role"] == "assistant"


def test_send_message_rejects_empty(repo_root: Path) -> None:
    """send_message raises ValueError for an empty message."""
    with pytest.raises(ValueError, match="cannot be empty"):
        chat_api.send_message(
            repo_root, session_id="any", message="", model="glm-5.2",
        )


def test_send_message_rejects_unknown_model(repo_root: Path) -> None:
    """send_message raises ValueError for an unknown model."""
    with patch.object(chat_api, "_call_model", return_value=("initial", {})):
        result = chat_api.start_chat_session(
            repo_root, intent="start", model="glm-5.2",
        )
    with pytest.raises(ValueError, match="Unknown model"):
        chat_api.send_message(
            repo_root, session_id=result["session_id"], message="hi", model="nonexistent-model-xyz",
        )


def test_send_message_rejects_unlinked_session(repo_root: Path) -> None:
    with pytest.raises(ValueError, match="Unknown brainstorm session"):
        chat_api.send_message(
            repo_root, session_id="unlinked-session", message="hi", model="glm-5.2",
        )


def test_send_message_syncs_brainstorm_md(repo_root: Path) -> None:
    """send_message syncs the brainstorm.md artifact in the pipeline run."""
    with patch.object(chat_api, "_call_model", return_value=("r1", {})):
        result = chat_api.start_chat_session(
            repo_root, intent="idea here", model="glm-5.2",
        )
    sid = result["session_id"]
    run_id = result["run_id"]

    with patch.object(chat_api, "_call_model", return_value=("r2", {})):
        chat_api.send_message(
            repo_root, session_id=sid, message="more", model="glm-5.2",
        )

    md_path = repo_root / ".devflow" / "pipeline-runs" / run_id / "brainstorm.md"
    assert md_path.exists()
    md = md_path.read_text()
    assert "idea here" in md
    assert "r1" in md
    assert "r2" in md
    assert "more" in md


# ---------------------------------------------------------------------------
# Unselected-model routing
# ---------------------------------------------------------------------------

def test_unselected_chat_model_uses_brainstorm_role_router() -> None:
    """The chat fallback follows routing without pinning one frontier model."""
    with patch("devflow.loop.routing.resolve_role_compatible") as resolve:
        resolve.return_value.model_name = "operator-routed-frontier"

        model = chat_api._default_model()

    assert model == "operator-routed-frontier"
    resolve.assert_called_once_with("brainstorm")


# ---------------------------------------------------------------------------
# Message building
# ---------------------------------------------------------------------------

def test_build_messages_preserves_order() -> None:
    """_build_messages adds the role contract before transcript history."""
    transcript = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi there"},
        {"role": "user", "content": "bye"},
    ]
    messages = chat_api._build_messages(transcript)
    assert len(messages) == 4
    assert messages[0]["role"] == "system"
    assert "clarify" in messages[0]["content"].lower()
    assert "smallest" in messages[0]["content"].lower()
    assert messages[1] == {"role": "user", "content": "hello"}
    assert messages[2] == {"role": "assistant", "content": "hi there"}
    assert messages[3] == {"role": "user", "content": "bye"}


def test_build_messages_skips_empty_content() -> None:
    """_build_messages skips records with empty content."""
    transcript = [
        {"role": "user", "content": ""},
        {"role": "assistant", "content": "real"},
    ]
    messages = chat_api._build_messages(transcript)
    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert messages[1]["content"] == "real"


def test_hermes_output_strips_reasoning_and_session_metadata() -> None:
    raw = (
        "<think>private reasoning</think>\n"
        "Final Answer: useful answer\n"
        "session_id: hermes-123\n"
    )

    assert chat_api._strip_hermes_output(raw) == "useful answer"


# ---------------------------------------------------------------------------
# Page HTML sanity
# ---------------------------------------------------------------------------

def test_page_html_contains_chat_sidebar() -> None:
    """The status page HTML includes the chat sidebar elements."""
    from devflow.control_room.page import STATUS_PAGE_HTML
    assert "chat-sidebar" in STATUS_PAGE_HTML
    assert "chat-model-select" in STATUS_PAGE_HTML
    assert "sendChatMessage" in STATUS_PAGE_HTML
    assert "loadChatModels" in STATUS_PAGE_HTML
    assert "/api/chat/models" in STATUS_PAGE_HTML
    assert "/api/chat/start" in STATUS_PAGE_HTML
    assert "/api/chat/send" in STATUS_PAGE_HTML


def test_new_chat_session_hides_existing_status_runs_until_first_message() -> None:
    """A fresh brainstorm must not keep another session's status card visible."""
    from devflow.control_room.page import STATUS_PAGE_HTML

    def javascript_function(name: str) -> str:
        match = re.search(
            rf"function {name}\([^)]*\) \{{.*?^\}}",
            STATUS_PAGE_HTML,
            flags=re.MULTILINE | re.DOTALL,
        )
        assert match, f"Missing {name} from the status page script"
        return match.group(0)

    script = "\n".join([
        "let CHAT_AWAITS_FIRST_MESSAGE = false;",
        "let CHAT_SESSION_ID = 'previous-session';",
        "let CHAT_RUN_ID = 'previous-run';",
        "function setFocusedRun() {}",
        "function render() {}",
        "function renderChatMessages() {}",
        "const document = { getElementById: () => ({ value: '', focus() {} }) };",
        javascript_function("statusRunsForChatSession"),
        javascript_function("newChatSession"),
        "newChatSession();",
        "const visibleRuns = statusRunsForChatSession([{ run_id: 'previous-run' }]);",
        "if (visibleRuns.length !== 0) throw new Error('previous run remains visible');",
    ])
    result = subprocess.run(["node", "--input-type=commonjs", "-e", script], capture_output=True, text=True)

    assert result.returncode == 0, result.stderr
