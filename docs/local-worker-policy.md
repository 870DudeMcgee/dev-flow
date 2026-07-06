# Local Worker Policy

Status: active local-worker truth, accepted on 2026-07-04.

This document is the current selection rule for local model workers in Dev-Flow,
Hermes, and Codex sessions. Older docs may still describe legacy Dev-Flow
evidence surfaces, patch proposal workers, or historical experiment plans; those
details are not authority for current worker choice.

## Current Rule

Local workers are opt-in. Do not launch a local worker just because a task is
non-trivial, because a doc mentions scouts, or because an old plan used local
parallelism.

Use a local worker only when:

- the operator explicitly asks for local-worker help;
- the active task/session explicitly selects a local worker; or
- a local-worker diagnostic or verification step requires one.

When local-worker use is opted in, the normal lane is one Qwen 3.6 27B Q5 MTP
worker:

- Codex custom agent: `qwen36_27b_mtp_coder`
- Hermes lane: `qwen36_coder`
- provider/model tuple: `local_qwen36_27b_mtp_bare` /
  `qwen36-27b-q5-mtp`
- local endpoint: `http://127.0.0.1:8083/v1`

Use Qwen for bounded reading, coding, testing, review, patch/output authoring,
JSON/command-only output, and strict-output work after a real completion proves
the route is ready.

## Supported Workflow

In Codex, the supported local-worker workflow is a visible subagent spawn:

```text
multi_agent_v1.spawn_agent(agent_type="qwen36_27b_mtp_coder")
```

The required proof is the spawned subagent's output surfaced back into the
parent Codex session, such as a compact marker response from the worker. This
proves Codex tool exposure and local-worker routing at the session level.
Direct HTTP probes, Hermes MCP tests, and `/v1/models` checks can support
diagnosis, but they are not equivalent proof that the Codex subagent lane is
loaded.

In Hermes sessions, use `hermes-qwen-mtp` for the same bounded Qwen packet
semantics: call `qwen_ready(smoke=true)` before `qwen_run`. The MCP tool should
stay narrow: no file reads or writes, no model lifecycle tools, no resources,
and no prompts. Its output is worker evidence for the supervisor to review, not
final proof of completion.

If the Codex spawn surface is unavailable or rejects the custom agent, say that
explicitly before falling back to Hermes MCP or direct local HTTP diagnostics.

## Exceptions

Other local routes remain available only as explicit exceptions:

- Ornith 9B: read-only packet scout only when the operator explicitly asks for
  Ornith or a diagnostic requires that route.
- Hermes Ornith 9B: read-only scout only when the operator explicitly asks for
  that route or a diagnostic requires Hermes read-only file/search tools.
- Ornith 35B: hard read-only repo-analysis or review; no edits, patches, or
  strict machine output.
- MLX, Ollama, Qwopus, Qwen3-Coder-Next, and legacy Dev-Flow local patch
  workers: explicit diagnostics, product evidence surfaces, or historical
  compatibility paths, not normal routing defaults.

## Safety Invariants

- Run at most one big local model server at a time.
- Qwen 27B is single-lane.
- `/v1/models` and open ports are not readiness proof; use a real completion.
- Codex session proof requires a visible spawned `qwen36_27b_mtp_coder`
  subagent response, not only CLI or MCP discovery.
- Worker output is evidence, not proof.
- The supervisor/main agent owns semantic review, final verification, and
  claims of completion.
- MCP fleet telemetry stays disabled unless the current session needs it.
- Active smoke completions are decision-point proof, not routine inventory.

## Current Authority Chain

Use this chain when docs disagree:

1. Current human instruction.
2. [AGENTS.md](../AGENTS.md) local worker policy.
3. This policy.
4. [ADR 0001](adr/0001-efficiency-first-local-worker-protocol.md).
5. `local-subagent-workers` skill references under
   `/Users/jewelbait/.codex/skills/local-subagent-workers/`.
6. Historical plans, rollout docs, and older architecture notes.

Historical docs should preserve evidence, but they must not reintroduce
local-scout-by-default, multi-route routing menus, or automatic worker selection.
