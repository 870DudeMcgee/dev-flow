# Local Worker Policy

Status: active local-worker truth, updated on 2026-07-06.

This document is the current selection rule for local model workers in Dev-Flow,
Hermes, and Codex sessions. Older docs may still describe legacy Dev-Flow
evidence surfaces, patch proposal workers, or historical experiment plans; those
details are not authority for current worker choice.

## Current Rule

Local workers are opt-in. Do not launch a local worker just because a task is
non-trivial, because a doc mentions scouts, or because an old plan used local
parallelism.

Repo loop cockpit note, 2026-07-06: Ornith 9B is excluded from active Dev-Flow
loop routing because it adds setup/routing complexity without useful value for
the guided cockpit. Any remaining Ornith 9B references below are explicit
diagnostic or non-cockpit exceptions, not defaults or fallbacks for the new
pipeline.

Deterministic Hermes tool lanes, such as parser/extractor/verifier scripts, are
not local model workers. Use those tool lanes for mechanical repo operations
before considering a local model route.

Use a local worker only when:

- the operator explicitly asks for local-worker help;
- the active task/session explicitly selects a local worker; or
- a local-worker diagnostic or verification step requires one.

When local-worker use is opted in, use the routed three-model fleet:

- Qwen3-Coder-Next on `8084`: builder/coder for code generation,
  refactoring, debugging, codebase surveys, and context compression. It is
  non-thinking mode only.
- Qwen 27B MTP on `8083`: judge for review, validation, final approval, and
  strict-output checks. It runs with thinking mode on.
- Ornith 35B on `8086`: scout for AST scans, file surveys, and deterministic
  codebase inspection.

Use `~/.hermes/scripts/model-router start <name>` and let the router handle
starts, stops, and swaps. Fleet status is informational, not gating.

## Supported Workflow

In Codex, the supported local-worker workflow is a visible subagent spawn:

```text
multi_agent_v1.spawn_agent(agent_type="qwen3_coder_next_coder")  # builder
multi_agent_v1.spawn_agent(agent_type="qwen36_27b_mtp_coder")   # judge/review
```

The required proof is the spawned subagent's output surfaced back into the
parent Codex session, such as a compact marker response from the worker. This
proves Codex tool exposure and local-worker routing at the session level.
Direct HTTP probes, Hermes MCP tests, and `/v1/models` checks can support
diagnosis, but they are not equivalent proof that the Codex subagent lane is
loaded.

In Hermes sessions, use the fleet profile or wrapper that matches the role
described in [docs/fleet-routing-brief.md](fleet-routing-brief.md). The MCP
tool should stay narrow: no unrequested file reads or writes, no manual model
lifecycle commands, and no bypass around the router. Its output is worker
evidence for the supervisor to review, not final proof of completion.

If the Codex spawn surface is unavailable or rejects the custom agent, say that
explicitly before falling back to Hermes MCP or direct local HTTP diagnostics.

## Exceptions

Other local routes remain available only as explicit exceptions:

- Ornith 9B and Hermes Ornith 9B: retired from active routing and fallback
  paths. Treat any remaining references as historical unless the operator gives
  explicit one-off approval for a diagnostic.
- Ornith 35B: current scout lane on `8086`; no edits, patches, code
  generation, or strict machine output.
- MLX, Ollama, Qwopus, and legacy Dev-Flow local patch workers: explicit
  diagnostics, product evidence surfaces, or historical compatibility paths,
  not normal routing defaults.

## Safety Invariants

- Run at most one big local model server at a time.
- The model-router handles swaps between Qwen3-Coder-Next, Qwen 27B, and
  Ornith 35B.
- Qwen3-Coder-Next is non-thinking mode only.
- Qwen 27B runs thinking mode for judging.
- `/v1/models` and open ports are not readiness proof; use a real completion.
- Codex session proof requires a visible spawned subagent response, not only
  CLI or MCP discovery.
- Worker output is evidence, not proof.
- The supervisor/main agent owns semantic review, final verification, and
  claims of completion.
- MCP fleet telemetry stays disabled unless the current session needs it.
- Active smoke completions are decision-point proof, not routine inventory.

## Compression Lane

Codex sessions should route large files and large command output through the
local-fleet-efficiency compression tools before reading them in frontier
context. The normal compression lane is Qwen3-Coder-Next on `8084`; Ornith 35B
on `8086` is the scout lane for AST scans and file surveys.

Use:

```bash
python3 ~/.hermes/skills/software-development/local-fleet-efficiency/scripts/compress_tool_output.py
python3 ~/.hermes/skills/software-development/local-fleet-efficiency/scripts/extract_methods.py
python3 ~/.hermes/skills/software-development/local-fleet-efficiency/scripts/codebase_survey.py
```

Qwen3-Coder-Next should not produce `<think>` blocks. Ornith 9B is not a
compression fallback.

The repo-level first-read workflow is
[docs/codex-efficient-workflow.md](codex-efficient-workflow.md).

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
