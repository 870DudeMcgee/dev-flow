# Hermes Worker Runtime Supervisor Loop Implementation Plan

Date: 2026-06-21
Status: implemented locally through Slice 7; pending scoped commit(s) and push approval
Scope: implementation slices use packet-only, dry-run, or fake-Hermes test paths. No live Hermes/provider/model launch is required for verification, and no git stage/commit/push was performed by this documentation closure.

> **For Hermes:** Use `devflow-analysis`, `hermes-agent`, and `subagent-driven-development` before implementation. This plan is a DevFlow handoff: implement slice-by-slice with a supervisor worker loop. Worker self-report is not proof; the supervisor owns diff review, allowlist checks, verification, commits, and push decisions.

## Goal

Make DevFlow call bounded Hermes worker profiles instead of treating raw GPT/Qwen/DeepSeek calls as the primary worker runtime, while preserving DevFlow as the source of truth for task state, packet evidence, serial phase order, verification, and promotion gates.

## Architecture

DevFlow remains the state machine and evidence authority. Hermes becomes an execution runtime adapter: DevFlow creates a serial local-agent packet, then an approved launcher may run `hermes -p <profile> chat -q <bounded packet prompt>` under the same single-flight and completion-verifier gates. The model behind the Hermes profile can be local Qwen/Qwopus, DeepSeek, GLM, or another provider without changing DevFlow's task-flow contracts.

## Product Contract

Current protected flow:

```text
Idea / Brainstorm
  -> Spec / Plan artifacts
  -> Implementation artifact
  -> Task creation + implementation context
  -> Worker options
  -> SerialLocalRun packet
  -> Hermes worker profile launch
  -> Completion verifier
  -> Review / verify / promote gates
```

Every arrow must leave both a durable artifact and one visible next safe action. No stage is complete if the operator is left at a hidden/manual dead end.

## Current Source Surfaces Inspected

| Surface | Current role | Finding |
|---|---|---|
| `src/devflow/control_room/serial_local_agent_run.py` | Writes packet-only run directories, preflight, `worker-packet.md`, `completion-verifier.py`, and read-only snapshot data. | Strong base. It intentionally has no launcher and records `model_launch: false`. Extend this instead of replacing it. |
| `src/devflow/cli.py` | Exposes `devflow agent serial-packet`, `agent run`, `agent advise`, and `agent propose-patch`. | `serial-packet` is the right producer for Hermes launch packets. `agent run --task --profile` still calls raw/local model worker-pool code, not Hermes. |
| `src/devflow/control_room/local_model_worker_pool.py` | Calls local model endpoints directly through `LocalModelClient`; writes read-only WorkerEvidence. | This is useful evidence/advisory infrastructure, but it is not the desired primary code-worker runtime if Hermes profile execution is better. |
| `src/devflow/control_room/agent_runtime.py` | Resolves agent execution surfaces: `agent_run`, `agent_advise`, `agent_propose_patch`, `task_run`, `packet_only`. | Add a Hermes execution surface rather than overloading raw local worker-pool semantics. |
| `src/devflow/control_room/worker_options.py` | Projects AI worker options and shell fallback into task workbench. | Backend projection exists, but options are currently model/worker oriented and do not express “create Hermes packet / launch Hermes profile” cleanly. |
| `src/devflow/control_room/operating_layer_script.py` | Renders launchpad worker panel. | `renderWorkerOptions()` currently only renders the shell/start capability. This is the main producer-to-UI disconnect for worker choices. |
| `src/devflow/control_room/operating_layer_server.py` | Runs exact approval-gated browser commands. | Browser direct execution is intentionally limited to shell worker runs, verification, promotion, etc. It blocks provider/local-model-looking shell commands. Keep Hermes runtime launch out of browser at first. |
| `src/devflow/control_room/orchestration_plan.py` | Defines serial phase contract: implementer -> verifier -> tiny_repair -> supervisor_final_gate. | Reuse the phase order and final-gate ownership. Do not invent a second supervision contract. |
| `.devflow/agents/registry.yaml` + `agent_registry.py` | Agent/profile registry with permission modes, writes, `hermes_delegable`, and runtime checks. | Existing `hermes_delegable` means “safe for Hermes to request/read” in current policy, not “launch Hermes as the worker.” Add explicit semantics before enabling execution. |

Read-only status check at planning time: `main` was clean and even with `origin/main`; no active/blocked DevFlow tasks or failed verification were reported.

## Key Design Decision

Treat a raw model as a stateless function call, and a Hermes profile as the worker runtime.

```text
raw model call = cheap advisory/classification function
Hermes worker profile = bounded autonomous operator with tools, skills, memory/context policy, and verification habits
```

DevFlow should therefore call:

```text
Hermes profile with Qwen/DeepSeek/GLM/etc. configured underneath
```

not:

```text
Qwen/DeepSeek/GLM directly as the normal code-worker path
```

## Safety Invariants

1. DevFlow remains source of truth for task state, `.devflow` evidence, serial phase state, verification, and promotion.
2. Hermes workers may be powerful, but their self-report is never final proof.
3. `completion-verifier.py` remains the independent proof gate for packet runs.
4. Local heavy models remain single-flight by provider/model lock.
5. Browser UI may create/read packet evidence after exact approval, but should not directly launch Hermes/local model execution in the first implementation milestone.
6. No worker may stage, commit, push, promote, clean, reset, or mutate canonical task state.
7. Allowed-file scope must be machine-checkable before and after launch.
8. If three repair attempts fail, block/escalate instead of relaunching broad packets.

## Proposed Runtime Contract

Extend `SerialLocalRun` with optional runtime metadata:

```json
{
  "runtime": {
    "kind": "hermes-profile",
    "hermes_profile": "qwen-worker",
    "toolsets": ["file", "terminal", "search", "skills"],
    "packet_only": true
  },
  "provider": "ollama",
  "model": "qwen3.6-32b-256k:latest",
  "safety": {
    "packet_only": true,
    "model_launch": false,
    "git_mutation": false,
    "promotion": false
  }
}
```

Then add launch evidence when a separate command runs the packet:

```json
{
  "runtime_kind": "hermes-profile",
  "hermes_profile": "qwen-worker",
  "run_id": "...",
  "packet_path": ".devflow/local-agent-runs/<run-id>/worker-packet.md",
  "stdout_path": ".devflow/local-agent-runs/<run-id>/hermes-stdout.txt",
  "stderr_path": ".devflow/local-agent-runs/<run-id>/hermes-stderr.txt",
  "session_hint": "... if available ...",
  "started_at": "...",
  "finished_at": "...",
  "exit_code": 0
}
```

`run.json` should remain the manifest. Runtime execution details can live in `hermes-run.json` to avoid rewriting the original packet contract in place more than necessary.

---

# Implementation Slices

## Slice 1 — Runtime Metadata On Serial Packets

**Goal:** Let packet creation declare that the intended runtime is a Hermes profile while still doing packet-only evidence.

Allowed files:

```text
src/devflow/control_room/serial_local_agent_run.py
tests/test_serial_local_agent_run.py
src/devflow/cli.py
tests/test_agent_cli.py
```

Implementation notes:

- Add optional parameters to `create_serial_local_agent_run(...)`:
  - `runtime_kind: str = "manual"`
  - `hermes_profile: str | None = None`
  - `toolsets: Sequence[str] | None = None`
- Extend `devflow agent serial-packet` with:
  - `--runtime manual|hermes-profile`
  - `--hermes-profile <profile>`
  - optional repeated `--toolset <name>`
- Keep `model_launch: false`, `worker_ran: no`, and `git_mutation: false` for packet creation.
- Worker packet should say: “This packet is intended for Hermes profile `<profile>`, but packet creation did not launch it.”

Tests:

```bash
env PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_serial_local_agent_run.py tests/test_agent_cli.py -q
```

Acceptance:

- Packet-only behavior remains unchanged for default manual runtime.
- Hermes-profile runtime metadata appears when requested.
- Missing `--hermes-profile` with `--runtime hermes-profile` fails clearly.
- No source files are changed except packet artifacts during test-created scratch repos.

## Slice 2 — Hermes Run Launcher, Dry-Run First

**Goal:** Add a launcher module and CLI surface that can validate a packet and preview the exact Hermes command without starting Hermes.

Allowed files:

```text
src/devflow/control_room/hermes_worker_runtime.py
src/devflow/cli.py
tests/test_hermes_worker_runtime.py
tests/test_agent_cli.py
```

Command shape:

```bash
devflow agent hermes-run <run-id> --profile qwen-worker --dry-run --json
```

Dry-run output should include:

```json
{
  "will_launch_hermes": false,
  "run_id": "...",
  "packet_path": ".../worker-packet.md",
  "hermes_profile": "qwen-worker",
  "command_preview": ["hermes", "-p", "qwen-worker", "chat", "-q", "..."],
  "preflight_state": "free",
  "launch_allowed": true
}
```

Tests:

```bash
env PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_hermes_worker_runtime.py tests/test_agent_cli.py -q
```

Acceptance:

- Dry-run never invokes `hermes`.
- Dry-run refuses missing packet, stale/running same model lock, missing `worker-packet.md`, and non-Hermes runtime packets unless explicitly forced.
- Command preview is argv-list based, not shell-string based, to avoid quoting bugs.

## Slice 3 — Real Hermes Launch With Fake-Hermes Test Harness

**Goal:** Implement the non-dry-run launcher using a fake executable in tests, not a live Hermes/provider/model call.

Allowed files:

```text
src/devflow/control_room/hermes_worker_runtime.py
tests/test_hermes_worker_runtime.py
src/devflow/cli.py
```

Implementation notes:

- Add `--hermes-bin hermes` mainly for tests and explicit operator overrides.
- Use `subprocess.run(argv, cwd=root, capture_output=True, text=True, timeout=...)`.
- Acquire/reuse provider/model single-flight lock before launch when packet provider/model are local/heavy.
- Write:
  - `hermes-run.json`
  - `hermes-stdout.txt`
  - `hermes-stderr.txt`
- Update launch status evidence, but do not claim verification success.
- The launcher should print next safe action: run the packet `completion-verifier.py`.

Tests:

```bash
env PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_hermes_worker_runtime.py tests/test_local_model_runtime_lock.py -q
```

Acceptance:

- Fake Hermes receives the packet prompt and profile argv.
- Stdout/stderr/exit code are captured.
- Nonzero exit writes failed launch evidence and exits nonzero.
- Lock is acquired during launch and released after process exit.
- Launcher does not run `completion-verifier.py` automatically.

## Slice 4 — Supervisor Policy And Browser Boundaries

**Goal:** Make the new commands explicit in supervisor classification without accidentally allowing browser model execution.

Allowed files:

```text
src/devflow/control_room/supervisor_surface.py
src/devflow/control_room/browser_action_policy.py
src/devflow/control_room/operating_layer_server.py
tests/test_supervisor_classify_cli.py
tests/test_supervisor_operating_surface.py
tests/test_operator_ui_browser.py
```

Policy recommendation:

- `devflow agent serial-packet ... --runtime hermes-profile ...` = approval-required evidence writing.
- `devflow agent hermes-run ... --dry-run` = pure read-only or approval-required evidence preview, depending whether it writes preview evidence.
- `devflow agent hermes-run ...` without `--dry-run` = approval-required worker runtime, but **not browser-executable in the first milestone**.

Acceptance:

- Browser policy says packet creation may be approved, Hermes/local model launch remains blocked from browser execution.
- `/api/actions/run` does not accept non-dry-run `agent hermes-run`.
- The policy text explains the boundary so the UI does not imply a broken button.

## Slice 5 — WorkerOptions -> Launchpad Rendering

**Goal:** Connect existing backend worker options to the operator-facing launchpad.

Allowed files:

```text
src/devflow/control_room/worker_options.py
src/devflow/control_room/task_workbench.py
src/devflow/control_room/operating_layer_script.py
src/devflow/control_room/operating_layer_styles.py
tests/test_worker_options_projection.py
tests/test_operator_ui_browser.py
```

Implementation notes:

- `renderWorkerOptions(task)` should consume `task.worker_options`, not only `start_shell` capability.
- AI/Hermes options should show above shell fallback.
- Enabled local/Hermes options should produce a packet-creation action, not direct browser launch.
- Shell fallback remains available but secondary.

Suggested UI copy:

```text
Recommended worker
Hermes Qwen Implementer
Creates a bounded serial packet for qwen-worker. Launch remains outside browser; verifier is final proof.
```

Acceptance:

- A task with `worker_options` renders at least one AI/Hermes worker card.
- Shell fallback still renders and still uses existing exact approval phrase.
- Browser test checks text and data attributes; it does not start Hermes.

## Slice 6 — Snapshot Status For Hermes Runtime Runs

**Goal:** Project latest Hermes launch evidence into `serial_local_agent_run` so the operator sees whether the packet is pending, launched, failed, or ready for verifier.

Allowed files:

```text
src/devflow/control_room/serial_local_agent_run.py
src/devflow/control_room/hermes_worker_runtime.py
src/devflow/control_room/operating_layer.py
tests/test_serial_local_agent_run.py
tests/test_operating_layer.py
```

Acceptance:

- Snapshot includes `runtime_kind`, `hermes_profile`, `launch_status`, `exit_code`, and evidence paths when `hermes-run.json` exists.
- `browser_actions` remains empty or packet-only until a separate policy slice approves browser packet creation.
- `next_safe_action` changes from “launch manually” to “run completion-verifier.py” after a launch exits cleanly.

## Slice 7 — Documentation Closure

Allowed files:

```text
docs/local-model-runtime.md
docs/superpowers/plans/2026-06-21-hermes-worker-runtime-supervisor-loop.md
```

Acceptance:

- Document the distinction:
  - raw local model worker-pool = advisory/read-only evidence;
  - Hermes worker runtime = bounded operator launched from a serial packet;
  - DevFlow verifier/final gate remains source of truth.
- Add command examples for dry-run, launch, and verifier.
- Mark this plan complete only after focused tests pass and implementation commits exist.

---

# Focused Verification Set

Run via the project wrapper if available; otherwise use the existing project test convention shown in adjacent plans:

```bash
env PYTHONPATH=src:. .venv/bin/python -m pytest \
  tests/test_serial_local_agent_run.py \
  tests/test_hermes_worker_runtime.py \
  tests/test_agent_cli.py \
  tests/test_worker_options_projection.py \
  tests/test_supervisor_classify_cli.py \
  tests/test_supervisor_operating_surface.py \
  tests/test_operating_layer.py \
  tests/test_operator_ui_browser.py \
  -q
```

Also run:

```bash
git diff --check
env PYTHONPATH=src:. .venv/bin/python -m py_compile \
  src/devflow/control_room/serial_local_agent_run.py \
  src/devflow/control_room/hermes_worker_runtime.py \
  src/devflow/cli.py
```

If browser dependencies are unavailable, record the exact dependency blocker and run the non-browser focused set.

---

# Local Closure Record

Slice 7 updated the operator documentation for the Hermes runtime boundary. The implementation is intentionally **not** marked complete yet because scoped implementation commits do not exist in this working tree.

| Slice | Local outcome | Commit |
|---|---|---|
| Slice 1 — Runtime metadata | Implemented in working tree. | pending scoped commit |
| Slice 2 — Dry-run launcher | Implemented in working tree. | pending scoped commit |
| Slice 3 — Fake-Hermes launch harness | Implemented in working tree. | pending scoped commit |
| Slice 4 — Supervisor/browser policy | Implemented in working tree. | pending scoped commit |
| Slice 5 — Launchpad rendering | Implemented in working tree. | pending scoped commit |
| Slice 6 — Snapshot projection | Implemented in working tree. | pending scoped commit |
| Slice 7 — Documentation closure | Implemented in working tree. | pending scoped commit |

Documentation command examples now live in `docs/local-model-runtime.md` and cover packet creation, dry-run preview, manual Hermes launch, and `completion-verifier.py`.

## Next Safe Action

Review the full dirty tree, then request explicit approval for scoped commits. Keep implementation and documentation commits scoped to this plan's allowlist. Do not push without a separate explicit push approval.
