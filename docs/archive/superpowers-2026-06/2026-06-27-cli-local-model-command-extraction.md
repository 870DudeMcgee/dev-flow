# CLI Local Model Command Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce the highest-ranked architecture hotspot, `src/devflow/cli.py`, by extracting the cohesive `devflow local-model` command group into a dedicated command module with no behavior change.

**Architecture:** Follow the existing `devflow.control_room.dogfood_command` pattern: the command module owns a `Typer` sub-app, command handlers, and local error handling; `src/devflow/cli.py` only imports and mounts the sub-app. This is a first bounded cleanup slice for the #1 Graphify target, not a broad CLI redesign.

**Tech Stack:** Python, Typer, pytest, Graphify-generated architecture evidence.

---

## Context

Fresh Graphify checkpoint: `docs/architecture/control-room-architecture-audit.md`

Current hotspot evidence:

- `src/devflow/cli.py`: 4,843 lines, 180 definitions, 137 local imports, boundary target: yes
- Recommended cleanup target rank: #1

Selected slice:

- Extract `local_model_app` and the four `local-model` command handlers currently near `src/devflow/cli.py:255-371`.
- Keep `devflow local-model status|stop|start|restart` output, options, errors, and exit codes unchanged.

Non-goals:

- Do not refactor `src/devflow/control_room/local_model_server.py`.
- Do not touch local model runtime locks, worker execution, agent registry, operating-layer UI, or provider behavior.
- Do not extract unrelated `cli.py` command groups in this task.
- Do not commit generated `graphify-out/` artifacts.

## File Structure

- Create: `src/devflow/control_room/local_model_command.py`
  - Owns the `local_model_app` Typer sub-app declaration.
  - Owns `status`, `stop`, `start`, and `restart` Typer handlers.
  - Imports `devflow.control_room.local_model_server` inside handlers, preserving current lazy import behavior.
- Modify: `src/devflow/cli.py`
  - Import `local_model_app` from `devflow.control_room.local_model_command`.
  - Remove the inline `local_model_app` Typer sub-app declaration.
  - Remove the four inline `local_model_app` command handlers.
  - Keep `app.add_typer(local_model_app, name="local-model")`.
- Create: `tests/test_local_model_command.py`
  - Directly tests the extracted command app without going through the root CLI.
- Existing tests: `tests/test_local_model_server.py`
  - Keep existing root CLI coverage for `devflow local-model status` and `devflow local-model stop`.
- Modify: `docs/architecture/control-room-architecture-audit.md`
  - Only if the final Graphify audit changes checkpoint metrics.

---

### Task 1: Add Direct Command-Module Tests

**Files:**
- Create: `tests/test_local_model_command.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_local_model_command.py` with this exact content:

```python
from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from devflow.control_room.local_model_command import local_model_app


QWEN_PS_OUTPUT = """
24842 1 S 123456 /opt/homebrew/bin/llama-server --hf-repo unsloth/Qwen3.6-9B-MTP-GGUF:UD-Q4_K_XL --no-mmproj --alias qwen36-27b-q5-mtp --host 127.0.0.1 --port 8080 --ctx-size 65536 --no-webui
"""


def test_local_model_command_status_json_reports_running_process(monkeypatch: pytest.MonkeyPatch) -> None:
    from devflow.control_room import local_model_server

    monkeypatch.setattr(
        local_model_server,
        "list_local_model_server_processes",
        lambda include_ollama=False: local_model_server.parse_local_model_server_processes(QWEN_PS_OUTPUT),
    )

    result = CliRunner().invoke(local_model_app, ["status", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["action"] == "status"
    assert payload["running_count"] == 1
    assert payload["processes"][0]["pid"] == 24842
    assert payload["processes"][0]["model"] == "qwen36-27b-q5-mtp"


def test_local_model_command_stop_dry_run_accepts_no_profile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from devflow.control_room import local_model_server

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        local_model_server,
        "list_local_model_server_processes",
        lambda include_ollama=False: local_model_server.parse_local_model_server_processes(QWEN_PS_OUTPUT),
    )

    result = CliRunner().invoke(local_model_app, ["stop", "--dry-run", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "would_stop"
    assert payload["processes"][0]["pid"] == 24842
```

- [ ] **Step 2: Run the new tests to confirm the current failure**

Run:

```bash
env PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_local_model_command.py -q
```

Expected:

```text
ModuleNotFoundError: No module named 'devflow.control_room.local_model_command'
```

- [ ] **Step 3: Commit the test if this is an isolated task branch**

Run only when the execution environment expects local commits:

```bash
git add tests/test_local_model_command.py
git commit -m "test: cover local model command module"
```

Skip the commit when operating in a no-commit handoff flow.

---

### Task 2: Extract the Local Model Command Module

**Files:**
- Create: `src/devflow/control_room/local_model_command.py`

- [ ] **Step 1: Create the command module**

Create `src/devflow/control_room/local_model_command.py` with this exact content:

```python
from __future__ import annotations

import json
from pathlib import Path

import typer


local_model_app = typer.Typer(help="Manage local model server lifecycle")


@local_model_app.command("status")
def local_model_status_command(
    json_output: bool = typer.Option(False, "--json", help="Print local model server status as JSON."),
    include_ollama: bool = typer.Option(False, "--include-ollama", help="Include Ollama server processes in status."),
) -> None:
    """Show resident local model server processes."""
    from devflow.control_room import local_model_server

    payload = local_model_server.local_model_server_status(include_ollama=include_ollama)
    payload["action"] = "status"
    if json_output:
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
        return
    for line in local_model_server.render_local_model_server_lines(payload):
        typer.echo(line)


@local_model_app.command("stop")
def local_model_stop_command(
    profile: str | None = typer.Argument(None, help="Optional local server profile to stop, such as qwen36-27b-q5-mtp."),
    json_output: bool = typer.Option(False, "--json", help="Print stop result as JSON."),
    include_ollama: bool = typer.Option(False, "--include-ollama", help="Also stop Ollama server processes."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be stopped without sending signals."),
    timeout_seconds: float = typer.Option(15.0, "--timeout", min=0.0, help="Seconds to wait after SIGTERM."),
    no_kill: bool = typer.Option(False, "--no-kill", help="Do not escalate to SIGKILL after the timeout."),
) -> None:
    """Gracefully stop managed local model server processes."""
    from devflow.control_room import local_model_server

    try:
        payload = local_model_server.stop_local_model_servers(
            Path.cwd(),
            profile=profile,
            include_ollama=include_ollama,
            dry_run=dry_run,
            timeout_seconds=timeout_seconds,
            force_after_timeout=not no_kill,
        )
    except local_model_server.LocalModelServerError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    if json_output:
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
        return
    for line in local_model_server.render_local_model_server_lines(payload):
        typer.echo(line)


@local_model_app.command("start")
def local_model_start_command(
    profile: str = typer.Argument("qwen36-27b-q5-mtp", help="Local server profile to start."),
    json_output: bool = typer.Option(False, "--json", help="Print start result as JSON."),
    replace: bool = typer.Option(False, "--replace", help="Stop any managed local model server before starting this one."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show the launch command without starting anything."),
    host: str = typer.Option("127.0.0.1", "--host", help="Bind host for the local model server."),
    port: int = typer.Option(8080, "--port", min=1, max=65535, help="Bind port for the local model server."),
    binary: str = typer.Option("llama-server", "--binary", help="llama-server executable path."),
    no_wait: bool = typer.Option(False, "--no-wait", help="Do not wait for /v1/models readiness."),
    ready_timeout_seconds: float = typer.Option(60.0, "--ready-timeout", min=0.0, help="Seconds to wait for readiness."),
) -> None:
    """Start a managed local model server."""
    from devflow.control_room import local_model_server

    try:
        payload = local_model_server.start_local_model_server(
            Path.cwd(),
            profile,
            host=host,
            port=port,
            binary=binary,
            replace=replace,
            dry_run=dry_run,
            wait_for_ready=not no_wait,
            ready_timeout_seconds=ready_timeout_seconds,
        )
    except local_model_server.LocalModelServerError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    if json_output:
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
        return
    for line in local_model_server.render_local_model_server_lines(payload):
        typer.echo(line)


@local_model_app.command("restart")
def local_model_restart_command(
    profile: str = typer.Argument("qwen36-27b-q5-mtp", help="Local server profile to restart."),
    json_output: bool = typer.Option(False, "--json", help="Print restart result as JSON."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show the launch command without starting anything."),
    host: str = typer.Option("127.0.0.1", "--host", help="Bind host for the local model server."),
    port: int = typer.Option(8080, "--port", min=1, max=65535, help="Bind port for the local model server."),
    binary: str = typer.Option("llama-server", "--binary", help="llama-server executable path."),
    no_wait: bool = typer.Option(False, "--no-wait", help="Do not wait for /v1/models readiness."),
    ready_timeout_seconds: float = typer.Option(60.0, "--ready-timeout", min=0.0, help="Seconds to wait for readiness."),
) -> None:
    """Stop the current managed local model server, then start the requested profile."""
    from devflow.control_room import local_model_server

    try:
        payload = local_model_server.restart_local_model_server(
            Path.cwd(),
            profile,
            host=host,
            port=port,
            binary=binary,
            dry_run=dry_run,
            wait_for_ready=not no_wait,
            ready_timeout_seconds=ready_timeout_seconds,
        )
    except local_model_server.LocalModelServerError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    if json_output:
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
        return
    for line in local_model_server.render_local_model_server_lines(payload):
        typer.echo(line)
```

- [ ] **Step 2: Run the direct command-module tests**

Run:

```bash
env PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_local_model_command.py -q
```

Expected:

```text
2 passed
```

---

### Task 3: Thin `src/devflow/cli.py`

**Files:**
- Modify: `src/devflow/cli.py`

- [ ] **Step 1: Import the extracted sub-app**

In `src/devflow/cli.py`, add this import near the existing command-module imports:

```python
from devflow.control_room.local_model_command import local_model_app
```

Place it near:

```python
from devflow.control_room.dogfood_command import dogfood_app
```

- [ ] **Step 2: Remove the inline sub-app declaration**

Delete this line from the Typer app declarations:

```python
local_model_app = typer.Typer(help="Manage local model server lifecycle")
```

Keep this existing mount:

```python
app.add_typer(local_model_app, name="local-model")
```

- [ ] **Step 3: Remove the inline local-model command handlers**

Delete the four inline command functions from `src/devflow/cli.py`:

- `local_model_status_command`
- `local_model_stop_command`
- `local_model_start_command`
- `local_model_restart_command`

The deleted bodies should match the new `src/devflow/control_room/local_model_command.py` bodies exactly.

- [ ] **Step 4: Confirm `cli.py` only mounts the sub-app**

Run:

```bash
rg -n "local_model_app|@local_model_app" src/devflow/cli.py src/devflow/control_room/local_model_command.py
```

Expected shape:

```text
src/devflow/cli.py:<line>:from devflow.control_room.local_model_command import local_model_app
src/devflow/cli.py:<line>:app.add_typer(local_model_app, name="local-model")
src/devflow/control_room/local_model_command.py:<line>:local_model_app = typer.Typer(help="Manage local model server lifecycle")
src/devflow/control_room/local_model_command.py:<line>:@local_model_app.command("status")
src/devflow/control_room/local_model_command.py:<line>:@local_model_app.command("stop")
src/devflow/control_room/local_model_command.py:<line>:@local_model_app.command("start")
src/devflow/control_room/local_model_command.py:<line>:@local_model_app.command("restart")
```

- [ ] **Step 5: Run focused CLI parity tests**

Run:

```bash
env PYTHONPATH=src:. .venv/bin/python -m pytest \
  tests/test_local_model_command.py \
  tests/test_local_model_server.py::test_local_model_server_status_cli_reports_json \
  tests/test_local_model_server.py::test_local_model_server_stop_cli_accepts_no_profile_dry_run \
  -q
```

Expected:

```text
4 passed
```

- [ ] **Step 6: Commit the extraction if this is an isolated task branch**

Run only when the execution environment expects local commits:

```bash
git add src/devflow/cli.py src/devflow/control_room/local_model_command.py tests/test_local_model_command.py
git commit -m "refactor: extract local model CLI commands"
```

Skip the commit when operating in a no-commit handoff flow.

---

### Task 4: Verification and Architecture Evidence

**Files:**
- Modify: `docs/architecture/control-room-architecture-audit.md` only if refreshed metrics change
- Generated local only: `graphify-out/`

- [ ] **Step 1: Run syntax verification**

Run:

```bash
env PYTHONPATH=src:. .venv/bin/python -m compileall \
  src/devflow/cli.py \
  src/devflow/control_room/local_model_command.py
```

Expected:

```text
exit code 0
```

`compileall` may print file-specific compile lines or no lines for already-compiled files; exit code `0` is the required result.

- [ ] **Step 2: Run focused local-model tests**

Run:

```bash
env PYTHONPATH=src:. .venv/bin/python -m pytest \
  tests/test_local_model_command.py \
  tests/test_local_model_server.py \
  -q
```

Expected:

```text
all selected tests pass
```

- [ ] **Step 3: Run architecture-audit command tests**

Run:

```bash
env PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_architecture_audit.py -q
```

Expected:

```text
all selected tests pass
```

- [ ] **Step 4: Refresh Graphify checkpoint evidence**

Run:

```bash
env PYTHONPATH=src:. .venv/bin/python -m devflow.cli architecture audit --write-doc
```

Expected:

```text
Architecture audit completed.
diagnostic: ok issues=3
checkpoint: <repo-root>/docs/architecture/control-room-architecture-audit.md
```

- [ ] **Step 5: Confirm Graphify freshness**

Run:

```bash
git rev-parse --short HEAD
rg -n "Built from commit" graphify-out/GRAPH_REPORT.md
```

Expected:

```text
<short-head>
<line>:- Built from commit: `<short-head-or-longer-prefix>`
```

If the report still points to the previous commit because Graphify says no topology changes, run:

```bash
.venv/bin/graphify cluster-only . --no-viz --no-label
env PYTHONPATH=src:. .venv/bin/python -m devflow.cli architecture audit --write-doc
git rev-parse --short HEAD
rg -n "Built from commit" graphify-out/GRAPH_REPORT.md
```

Expected after the fallback:

```text
GRAPH_REPORT.md uses the current HEAD prefix.
```

- [ ] **Step 6: Run diff hygiene checks**

Run:

```bash
git diff --check
git status --short
git diff --stat
```

Expected tracked changes:

```text
M  src/devflow/cli.py
A  src/devflow/control_room/local_model_command.py
A  tests/test_local_model_command.py
M  docs/architecture/control-room-architecture-audit.md
```

The architecture doc may be absent from the changed list if metrics do not change. `graphify-out/` should not appear in normal `git status --short`.

- [ ] **Step 7: Inspect the final diff**

Run:

```bash
git diff -- src/devflow/cli.py src/devflow/control_room/local_model_command.py tests/test_local_model_command.py docs/architecture/control-room-architecture-audit.md
```

Expected:

- `src/devflow/cli.py` imports and mounts `local_model_app` but no longer defines local-model command handlers.
- `src/devflow/control_room/local_model_command.py` contains the moved handlers.
- `tests/test_local_model_command.py` directly covers the command module.
- `docs/architecture/control-room-architecture-audit.md`, if changed, only reflects refreshed Graphify metrics/hotspots.

---

## Completion Report Requirements

Use these headings in the handoff:

```text
## Status
## Outcome
## Files Changed
## Verification
## Risks
## Recommended Next Steps
## Next Safe Action
```

Mention:

- Whether `src/devflow/cli.py` line count decreased.
- Whether `devflow local-model status` and `devflow local-model stop --dry-run` stayed covered through root CLI tests.
- Whether Graphify freshness matched current `HEAD`.
- Whether `graphify-out/` stayed ignored/untracked.

## Next Cleanup Candidate After This

If this slice lands cleanly, the next `cli.py` slice should be another cohesive command group with existing focused tests. Good candidates are:

1. `loop_app` to `src/devflow/control_room/loop_command.py`, because `tests/test_loop_engine.py` already covers the root CLI.
2. `scheduler_app` to `src/devflow/control_room/scheduler_command.py`, because `tests/test_scheduler_projection.py` already covers command behavior.
3. `question_app` to `src/devflow/control_room/question_command.py`, because `tests/test_question_resume.py` already covers command behavior.

Do not start those in this task.
