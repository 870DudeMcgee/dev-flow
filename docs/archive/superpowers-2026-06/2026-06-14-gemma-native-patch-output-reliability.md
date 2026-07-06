# Gemma Native Patch Output Reliability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `gemma4-12b-qat-implementer` produce parseable local Ollama patch proposal evidence by using explicit native Gemma generation settings and clear failure diagnostics.

**Architecture:** Add a small `ollama_generation` settings/request boundary under `src/devflow/control_room/`, then route `OllamaChatWorkerAdapter` through it. Gemma patch agents use native `/api/chat` with thinking disabled and explicit context/output limits; non-Gemma patch agents keep `/api/generate` but receive explicit bounded options.

**Tech Stack:** Python 3, urllib-based local Ollama HTTP calls, Typer CLI through existing worker paths, pytest, Markdown docs.

---

## File Structure

- Create `src/devflow/control_room/ollama_generation.py`: deterministic settings and payload builder for local Ollama patch workers.
- Modify `src/devflow/control_room/ollama_worker.py`: use the settings/request builder, parse both `/api/generate` and `/api/chat` responses, record request metadata, and improve length-truncation diagnostics.
- Modify `tests/test_ollama_worker.py`: add focused mocked-request coverage for Gemma native chat, default generate settings, run metadata, and length diagnostics.
- Modify `docs/architecture/local-model-worker-pool.md`: document Gemma patch worker settings and current evidence-only dogfood blocker.
- Modify `docs/control-room-mvp.md`: align the stable-command text with the explicit Gemma local patch settings behavior after verification.
- Modify `docs/superpowers/plans/2026-06-13-milestone-16-agent-registry-runtime-hardening.md`: update Task 5B with the `task-0035` evidence-only blocker and point to this repair plan before Task 6 resumes.
- Create `docs/handoffs/2026-06-14-gemma-native-patch-output-reliability-complete.md` only when implementation and dogfood verification finish.

## Task 1: Add Failing Request-Settings Tests

**Files:**
- Modify: `tests/test_ollama_worker.py`

- [ ] **Step 1: Add helpers for local patch worker tests**

Add this helper block near the existing `test_registry_backed_qwopus_run_writes_patch_artifacts_and_can_apply` test:

```python
def _write_local_patch_registry(root: Path, *, agent_id: str, model: str) -> None:
    agents_dir = root / ".devflow" / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    (agents_dir / "registry.yaml").write_text(
        "version: 1\n"
        "providers:\n"
        "  ollama:\n"
        "    provider: ollama\n"
        "    adapter: ollama_chat\n"
        "    base_url: http://127.0.0.1:11434\n"
        "    default_timeout_seconds: 600\n"
        "    enabled: true\n"
        "agents:\n"
        f"  {agent_id}:\n"
        "    provider: ollama\n"
        f"    model: {model}\n"
        "    adapter: ollama_chat\n"
        "    role: implementation_worker\n"
        "    tier: strong_local\n"
        "    default_mode: workspace_write\n"
        "    execution_mode: automated\n"
        "    workspace: isolated_task_workspace\n"
        "    can_run_shell: false\n"
        "    can_use_network: false\n"
        "    can_promote: false\n"
        "    enabled: true\n",
        encoding="utf-8",
    )


def _ready_patch_response() -> bytes:
    return json.dumps(
        {
            "message": {
                "content": json.dumps(
                    {
                        "status": "ready",
                        "diff": (
                            "diff --git a/hello.txt b/hello.txt\n"
                            "--- a/hello.txt\n"
                            "+++ b/hello.txt\n"
                            "@@ -1 +1 @@\n"
                            "-Hello World\n"
                            "+Hello from Gemma\n"
                        ),
                        "touched_paths": ["hello.txt"],
                        "risk": "low",
                        "confidence": 0.88,
                    }
                )
            },
            "done": True,
            "done_reason": "stop",
            "prompt_eval_count": 64,
            "eval_count": 128,
        }
    ).encode("utf-8")
```

- [ ] **Step 2: Add the Gemma native chat test**

Add this test to `tests/test_ollama_worker.py`:

```python
def test_gemma_patch_worker_uses_native_chat_with_explicit_generation_options(tmp_path: Path) -> None:
    Path(tmp_path / "hello.txt").write_text("Hello World\n", encoding="utf-8")
    _write_local_patch_registry(
        tmp_path,
        agent_id="gemma4-12b-qat-implementer",
        model="gemma4:12b-it-qat",
    )
    task = create_task(tmp_path, "Gemma patch settings")

    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.read.return_value = _ready_patch_response()

    with patch("urllib.request.urlopen") as mock_urlopen, \
         patch("devflow.control_room.ollama_worker.build_context_pack", return_value={}):
        mock_urlopen.return_value.__enter__.return_value = mock_response
        result = run_shell_task(tmp_path, task.id, [], worker_adapter="gemma4-12b-qat-implementer")

    assert result.status == "complete"
    request = mock_urlopen.call_args.args[0]
    assert request.full_url == "http://127.0.0.1:11434/api/chat"
    payload = json.loads(request.data.decode("utf-8"))
    assert payload["model"] == "gemma4:12b-it-qat"
    assert payload["stream"] is False
    assert payload["think"] is False
    assert payload["format"] == "json"
    assert payload["options"]["temperature"] == 0.2
    assert payload["options"]["num_ctx"] == 8192
    assert payload["options"]["num_predict"] == 4096
    assert [message["role"] for message in payload["messages"]] == ["system", "user"]

    agent_dir = tmp_path / ".devflow" / "tasks" / task.id / "agents" / "gemma4-12b-qat-implementer"
    run_json = json.loads((agent_dir / "run.json").read_text(encoding="utf-8"))
    assert run_json["request_endpoint"] == "/api/chat"
    assert run_json["request_payload_shape"] == "native_chat_messages"
    assert run_json["request_options"] == {"num_ctx": 8192, "num_predict": 4096, "temperature": 0.2}
    assert run_json["native_chat_think"] is False
    assert run_json["request_format"] == "json"
    assert run_json["ollama_response"]["done_reason"] == "stop"
    assert "message" not in run_json["ollama_response"]
    assert "Hello from Gemma" in (agent_dir / "proposal.patch").read_text(encoding="utf-8")
```

- [ ] **Step 3: Add the non-Gemma generate settings test**

Add this test:

```python
def test_non_gemma_patch_worker_keeps_generate_endpoint_with_explicit_generation_options(tmp_path: Path) -> None:
    Path(tmp_path / "hello.txt").write_text("Hello World\n", encoding="utf-8")
    task = create_task(tmp_path, "Qwopus patch settings")

    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.read.return_value = json.dumps(
        {
            "response": json.dumps(
                {
                    "status": "ready",
                    "diff": (
                        "diff --git a/hello.txt b/hello.txt\n"
                        "--- a/hello.txt\n"
                        "+++ b/hello.txt\n"
                        "@@ -1 +1 @@\n"
                        "-Hello World\n"
                        "+Hello from Qwopus\n"
                    ),
                    "touched_paths": ["hello.txt"],
                    "risk": "low",
                    "confidence": 0.91,
                }
            ),
            "done": True,
            "done_reason": "stop",
            "prompt_eval_count": 64,
            "eval_count": 128,
        }
    ).encode("utf-8")

    with patch("urllib.request.urlopen") as mock_urlopen, \
         patch("devflow.control_room.ollama_worker.build_context_pack", return_value={}):
        mock_urlopen.return_value.__enter__.return_value = mock_response
        result = run_shell_task(tmp_path, task.id, [], worker_adapter="qwopus-implementer")

    assert result.status == "complete"
    request = mock_urlopen.call_args.args[0]
    assert request.full_url == "http://127.0.0.1:11434/api/generate"
    payload = json.loads(request.data.decode("utf-8"))
    assert payload["model"] == "qwopus:latest"
    assert payload["format"] == "json"
    assert payload["stream"] is False
    assert payload["options"] == {"num_ctx": 8192, "num_predict": 4096, "temperature": 0.2}

    agent_dir = tmp_path / ".devflow" / "tasks" / task.id / "agents" / "qwopus-implementer"
    run_json = json.loads((agent_dir / "run.json").read_text(encoding="utf-8"))
    assert run_json["request_endpoint"] == "/api/generate"
    assert run_json["request_payload_shape"] == "generate_prompt_system"
    assert run_json["request_options"] == {"num_ctx": 8192, "num_predict": 4096, "temperature": 0.2}
```

- [ ] **Step 4: Run red tests**

Run:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_ollama_worker.py::test_gemma_patch_worker_uses_native_chat_with_explicit_generation_options tests/test_ollama_worker.py::test_non_gemma_patch_worker_keeps_generate_endpoint_with_explicit_generation_options -q
```

Expected: fail because the Gemma request still uses `/api/generate` and run metadata does not include request settings.

## Task 2: Implement Ollama Generation Settings

**Files:**
- Create: `src/devflow/control_room/ollama_generation.py`
- Modify: `src/devflow/control_room/ollama_worker.py`

- [ ] **Step 1: Create `ollama_generation.py`**

Create `src/devflow/control_room/ollama_generation.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from devflow.control_room.agent_registry import AgentDefinition


OllamaEndpoint = Literal["generate", "chat"]

DEFAULT_PATCH_NUM_CTX = 8192
DEFAULT_PATCH_NUM_PREDICT = 4096
DEFAULT_PATCH_TEMPERATURE = 0.2

GEMMA_PATCH_AGENT_IDS = {"gemma4-12b-qat-implementer"}


@dataclass(frozen=True)
class OllamaPatchGenerationSettings:
    endpoint: OllamaEndpoint
    num_ctx: int = DEFAULT_PATCH_NUM_CTX
    num_predict: int = DEFAULT_PATCH_NUM_PREDICT
    temperature: float = DEFAULT_PATCH_TEMPERATURE
    think: bool = False
    format_json: bool = True

    @property
    def endpoint_path(self) -> str:
        return "/api/chat" if self.endpoint == "chat" else "/api/generate"

    @property
    def payload_shape(self) -> str:
        return "native_chat_messages" if self.endpoint == "chat" else "generate_prompt_system"

    def options(self) -> dict[str, int | float]:
        return {
            "num_ctx": self.num_ctx,
            "num_predict": self.num_predict,
            "temperature": self.temperature,
        }


def settings_for_ollama_patch_agent(agent_id: str, model: str, agent: AgentDefinition | None = None) -> OllamaPatchGenerationSettings:
    model_name = model.lower()
    if agent_id in GEMMA_PATCH_AGENT_IDS or model_name.startswith("gemma4:"):
        return OllamaPatchGenerationSettings(endpoint="chat")
    return OllamaPatchGenerationSettings(endpoint="generate")


def build_ollama_patch_request_payload(
    *,
    model: str,
    system_instruction: str,
    prompt: str,
    settings: OllamaPatchGenerationSettings,
) -> dict[str, Any]:
    if settings.endpoint == "chat":
        payload: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": prompt},
            ],
            "stream": False,
            "think": settings.think,
            "options": settings.options(),
        }
    else:
        payload = {
            "model": model,
            "prompt": prompt,
            "system": system_instruction,
            "stream": False,
            "options": settings.options(),
        }
    if settings.format_json:
        payload["format"] = "json"
    return payload
```

- [ ] **Step 2: Wire settings into `ollama_worker.py` imports**

Add these imports:

```python
from devflow.control_room.ollama_generation import (
    OllamaPatchGenerationSettings,
    build_ollama_patch_request_payload,
    settings_for_ollama_patch_agent,
)
```

- [ ] **Step 3: Track the selected agent definition**

Near the existing `provider_id = "ollama"` initialization, add:

```python
        selected_agent = None
        generation_settings = OllamaPatchGenerationSettings(endpoint="generate")
```

Inside the `if env_agent_id:` registry block, after `agent = registry.require_agent(env_agent_id)`, add:

```python
                selected_agent = agent
```

After model/provider resolution and before building the request URL, add:

```python
        generation_settings = settings_for_ollama_patch_agent(
            evidence_agent_id,
            model,
            selected_agent,
        )
```

- [ ] **Step 4: Replace the hard-coded `/api/generate` payload**

Replace the current `url` and `data` block with:

```python
        url = f"{base_url.rstrip('/')}{generation_settings.endpoint_path}"
        data = build_ollama_patch_request_payload(
            model=model,
            system_instruction=system_instruction,
            prompt=prompt,
            settings=generation_settings,
        )
        run_meta.update(
            {
                "request_endpoint": generation_settings.endpoint_path,
                "request_payload_shape": generation_settings.payload_shape,
                "request_options": generation_settings.options(),
                "request_format": "json" if generation_settings.format_json else None,
                "native_chat_think": generation_settings.think if generation_settings.endpoint == "chat" else None,
                "prompt_chars": len(prompt),
                "system_instruction_chars": len(system_instruction),
            }
        )
```

Keep the existing `urllib.request.Request` call, but let it use the new `url` and `data`.

- [ ] **Step 5: Keep log output explicit**

Replace the existing `run_meta["ollama_response"]` assignment after `urlopen` with:

```python
                run_meta["ollama_response"] = _ollama_response_metadata(res_body)
```

Add this helper near `_response_summary`:

```python
def _ollama_response_metadata(res_body: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in res_body.items() if k not in {"response", "message"}}
```

- [ ] **Step 6: Keep log output explicit**

Replace the existing connection log line with:

```python
            log.write(
                "Connecting to local Ollama on "
                f"{url} (model: {model}, timeout: {timeout}s, "
                f"num_ctx: {generation_settings.num_ctx}, "
                f"num_predict: {generation_settings.num_predict})...\n"
            )
```

- [ ] **Step 7: Run focused tests**

Run:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_ollama_worker.py::test_gemma_patch_worker_uses_native_chat_with_explicit_generation_options tests/test_ollama_worker.py::test_non_gemma_patch_worker_keeps_generate_endpoint_with_explicit_generation_options -q
```

Expected: pass.

## Task 3: Add Length-Truncation Diagnostics

**Files:**
- Modify: `tests/test_ollama_worker.py`
- Modify: `src/devflow/control_room/ollama_worker.py`

- [ ] **Step 1: Add a regression test for `task-0035` style output**

Add this test:

```python
def test_ollama_worker_malformed_json_reports_length_truncation(tmp_path: Path) -> None:
    Path(tmp_path / "hello.txt").write_text("Hello World\n", encoding="utf-8")
    _write_local_patch_registry(
        tmp_path,
        agent_id="gemma4-12b-qat-implementer",
        model="gemma4:12b-it-qat",
    )
    task = create_task(tmp_path, "Gemma truncated JSON")

    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.read.return_value = json.dumps(
        {
            "message": {"content": "{\""},
            "done": True,
            "done_reason": "length",
            "prompt_eval_count": 4095,
            "eval_count": 1,
        }
    ).encode("utf-8")

    with patch("urllib.request.urlopen") as mock_urlopen, \
         patch("devflow.control_room.ollama_worker.build_context_pack", return_value={}):
        mock_urlopen.return_value.__enter__.return_value = mock_response
        result = run_shell_task(tmp_path, task.id, [], worker_adapter="gemma4-12b-qat-implementer")

    assert result.status == "worker_failed"
    assert "Ollama stopped at length before returning complete JSON" in result.summary
    assert "eval_count=1" in result.summary

    agent_dir = tmp_path / ".devflow" / "tasks" / task.id / "agents" / "gemma4-12b-qat-implementer"
    assert (agent_dir / "raw_output.md").read_text(encoding="utf-8") == "{\""
    run_json = json.loads((agent_dir / "run.json").read_text(encoding="utf-8"))
    worker_failed = json.loads((agent_dir / "worker_failed.json").read_text(encoding="utf-8"))
    assert run_json["ollama_response"]["done_reason"] == "length"
    assert "num_predict" in run_json["request_options"]
    assert worker_failed["summary"] == run_json["summary"]
```

- [ ] **Step 2: Add a diagnostic helper in `ollama_worker.py`**

Add this helper near `_response_summary`:

```python
def _malformed_json_message(raw_output_path: Path, parse_error: Exception, response_meta: dict[str, Any]) -> str:
    base = f"Malformed JSON from local Ollama worker; inspect raw output at {raw_output_path}. Parser error: {parse_error}"
    done_reason = response_meta.get("done_reason")
    eval_count = response_meta.get("eval_count")
    prompt_eval_count = response_meta.get("prompt_eval_count")
    if done_reason == "length":
        detail = (
            "Ollama stopped at length before returning complete JSON "
            f"(prompt_eval_count={prompt_eval_count}, eval_count={eval_count})."
        )
        if isinstance(eval_count, int) and eval_count <= 1:
            detail += " The model emitted only the JSON prefix or an equivalent one-token response."
        return f"{base}. {detail}"
    return base
```

- [ ] **Step 3: Use the helper in the parse-failure branch**

In the parse-failure branch that currently builds `message = f"Malformed JSON ..."` replace that assignment with:

```python
            response_meta = _ollama_response_metadata(res_body)
            message = _malformed_json_message(raw_output_path, parse_error, response_meta)
```

- [ ] **Step 4: Run diagnostics tests**

Run:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_ollama_worker.py::test_ollama_worker_malformed_json_reports_length_truncation -q
```

Expected: pass.

## Task 4: Run Focused Regression Suite

**Files:**
- No source changes unless a regression fails.

- [ ] **Step 1: Run local patch and registry tests**

Run:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_ollama_worker.py tests/test_local_agent_discovery.py tests/test_agent_runtime.py tests/test_agent_registry.py -q
```

Expected: pass.

- [ ] **Step 2: Run whitespace check**

Run:

```bash
git diff --check
```

Expected: no output.

- [ ] **Step 3: Checkpoint the implementation**

Run:

```bash
PYTHONPATH=src:. .venv/bin/devflow git checkpoint --message "fix: make gemma patch output reliable" --yes
```

Expected: creates a checkpoint commit and leaves the tree clean.

## Task 5: Rerun Task 5B Dogfood With Gemma

**Files:**
- Evidence only under `.devflow/tasks/<task_id>/...`
- Modify docs only if the dogfood exposes stale active wording.

- [ ] **Step 1: Create a new dogfood task**

Run:

```bash
PYTHONPATH=src:. .venv/bin/devflow task create "Milestone 16 Gemma local patch runtime dogfood"
```

Expected: creates the next task id.

- [ ] **Step 2: Capture local inventory and selected-agent evidence**

Run:

```bash
PYTHONPATH=src:. .venv/bin/devflow agent discover-local --json
PYTHONPATH=src:. .venv/bin/devflow agent select-local <task_id> --role implementation_worker --json
```

Expected:

- installed inventory includes `gemma4:12b-it-qat`
- selected agent is `gemma4-12b-qat-implementer`
- selection evidence is written to `.devflow/tasks/<task_id>/agent-selection.json`

- [ ] **Step 3: Run the selected Gemma worker explicitly**

Run:

```bash
PYTHONPATH=src:. .venv/bin/devflow task run <task_id> --worker gemma4-12b-qat-implementer
```

Expected on success:

- `.devflow/tasks/<task_id>/agents/gemma4-12b-qat-implementer/proposal.patch` exists and is non-empty
- `.devflow/tasks/<task_id>/agents/gemma4-12b-qat-implementer/raw_output.md` contains parseable JSON text
- `.devflow/tasks/<task_id>/agents/gemma4-12b-qat-implementer/run.json` records `/api/chat`, `num_ctx: 8192`, `num_predict: 4096`, and `done_reason: stop`

Expected on failure:

- `.devflow/tasks/<task_id>/agents/gemma4-12b-qat-implementer/worker_failed.json` exists
- `run.json` records endpoint, options, and Ollama response metadata
- close the task `evidence-only` with the exact failure reason

- [ ] **Step 4: Continue the patch ladder only if `proposal.patch` exists**

Run these commands only when Step 3 produced a non-empty patch:

```bash
PYTHONPATH=src:. .venv/bin/devflow task review-patch <task_id> --agent gemma4-12b-qat-implementer
PYTHONPATH=src:. .venv/bin/devflow task patch-dry-run <task_id> --agent gemma4-12b-qat-implementer
PYTHONPATH=src:. .venv/bin/devflow task apply-patch <task_id> --agent gemma4-12b-qat-implementer
PYTHONPATH=src:. .venv/bin/devflow task verify <task_id> --shell "<focused verification command>"
PYTHONPATH=src:. .venv/bin/devflow task review-ready <task_id> --json
```

Expected: Dev-Flow preserves explicit review, dry-run, apply, verification, and review-readiness evidence. No command promotes, merges, pushes, or creates a pull request.

- [ ] **Step 5: Close evidence-only dogfood when there is no patch**

If Step 3 fails or produces no patch, run:

```bash
PYTHONPATH=src:. .venv/bin/devflow task close <task_id> --outcome evidence-only --reason "<exact observed reason>"
PYTHONPATH=src:. .venv/bin/devflow task show <task_id>
```

Expected: task is closed with an audit-visible reason and one next safe cleanup action.

## Task 6: Update Active Docs And Milestone 16 Handoff

**Files:**
- Modify: `docs/architecture/local-model-worker-pool.md`
- Modify: `docs/control-room-mvp.md`
- Modify: `docs/superpowers/plans/2026-06-13-milestone-16-agent-registry-runtime-hardening.md`
- Create: `docs/handoffs/2026-06-14-gemma-native-patch-output-reliability-complete.md`

- [x] **Step 1: Update local model worker-pool docs**

Add a concise paragraph to `docs/architecture/local-model-worker-pool.md` near the existing Gemma native chat paragraph:

```markdown
`gemma4-12b-qat-implementer` is the first Gemma local patch runtime profile. It uses native Ollama `/api/chat` with thinking disabled and explicit bounded generation settings (`num_ctx 8192`, `num_predict 4096`) so patch proposal output is parseable JSON evidence. It still only writes `proposal.patch`, `raw_output.md`, `result.md`, `run.json`, logs, questions, or worker failure evidence under the task-local agent directory; Dev-Flow still owns patch review, dry-run, application, verification, and promotion.
```

- [x] **Step 2: Update MVP current behavior wording**

In `docs/control-room-mvp.md`, update the registry-backed local patch paragraph so it names both current explicit patch profiles:

```markdown
The registry-backed local patch form is `devflow task run <task_id> --worker qwopus-implementer` or `devflow task run <task_id> --worker gemma4-12b-qat-implementer` when that model is installed and selected by explicit local-agent evidence.
```

Keep the rest of the paragraph clear that local patch workers only produce proposal evidence.

- [x] **Step 3: Update Milestone 16 Task 5B status**

In `docs/superpowers/plans/2026-06-13-milestone-16-agent-registry-runtime-hardening.md`, append a short Task 5B evidence note:

```markdown
**Task 5B update, 2026-06-14:** `task-0035` selected `gemma4-12b-qat-implementer` after the explicit registry entry was added, but the existing generic Ollama patch worker emitted only `{"` and stopped with `done_reason: length`, `prompt_eval_count: 4095`, and `eval_count: 1`. Direct probes proved `gemma4:12b-it-qat` returns valid JSON when `num_ctx` and `num_predict` are explicit. Resume Task 5B only after completing `docs/superpowers/plans/2026-06-14-gemma-native-patch-output-reliability.md`.
```

- [x] **Step 4: Write the completion handoff**

Create `docs/handoffs/2026-06-14-gemma-native-patch-output-reliability-complete.md` using the standard headings:

```markdown
# Gemma Native Patch Output Reliability Complete Handoff

## Status

complete

## Files Changed

- `src/devflow/control_room/ollama_generation.py` (added deterministic local Ollama patch generation settings and request payload builder)
- `src/devflow/control_room/ollama_worker.py` (routed Gemma patch agents through native chat, recorded request settings, and improved malformed JSON diagnostics)
- `tests/test_ollama_worker.py` (covered Gemma native chat settings, default generate settings, and length-truncation diagnostics)
- `docs/architecture/local-model-worker-pool.md` (documented Gemma patch worker settings)
- `docs/control-room-mvp.md` (aligned stable local patch worker wording)
- `docs/superpowers/plans/2026-06-13-milestone-16-agent-registry-runtime-hardening.md` (recorded Task 5B blocker and repair-plan link)
- `docs/handoffs/2026-06-14-gemma-native-patch-output-reliability-complete.md` (this handoff)

## Verification

- Record the focused pytest command from Task 4 with its actual pass/fail summary.
- Record `git diff --check` with its actual output.
- Record the dogfood command sequence from Task 5 with the exact task id and result.
- Record `PYTHONPATH=src:. .venv/bin/devflow git status` with its clean/ahead/behind state.

## Risks

- Local model output quality is still evidence, not verification.
- Gemma patch output can still fail on oversized or underspecified tasks; failures must remain explicit and task-local.

## Next Safe Action

- Resume Task 6 in `docs/superpowers/plans/2026-06-13-milestone-16-agent-registry-runtime-hardening.md`.
```

Do not commit the completion handoff until every Verification bullet contains a real command and observed result.

- [x] **Step 5: Run doc hygiene checks**

Run:

```bash
rg -n "T[B]D|T[O]DO|implement[ ]later|fill[ ]in[ ]details|Similar[ ]to[ ]Task|appropriate[ ]error[ ]handling|Write[ ]tests[ ]for[ ]the[ ]above" docs/superpowers/specs/2026-06-14-gemma-native-patch-output-reliability-design.md docs/superpowers/plans/2026-06-14-gemma-native-patch-output-reliability.md docs/handoffs/2026-06-14-gemma-native-patch-output-reliability-complete.md -S
git diff --check
```

Expected: `rg` has no matches and `git diff --check` has no output.

- [x] **Step 6: Checkpoint and push when explicitly approved**

Run:

```bash
PYTHONPATH=src:. .venv/bin/devflow git checkpoint --message "fix: stabilize gemma patch worker output" --yes
PYTHONPATH=src:. .venv/bin/devflow push-main
```

Expected: clean synced `main` after push.

## Self-Review

- The plan covers the observed `task-0035` blocker with request settings, parser diagnostics, dogfood, docs, and handoff.
- The implementation stays under `src/devflow/control_room/` except existing test and documentation files.
- Hermes remains out of runtime scope.
- The dogfood ladder remains explicit and human-reviewable.
- No step asks a worker to apply, verify, promote, merge, or push based on model output alone.
