# Local Worker Policy

Status: active local-worker truth, updated on 2026-07-06.
Related: [AGENTS.md](../AGENTS.md), [fleet-debrief.md](fleet-debrief.md), [fleet-contract.json](../.devflow/fleet-contract.json)

This document is the current selection rule for local model workers in Dev-Flow,
Hermes, and Codex sessions. Older docs may describe legacy evidence surfaces,
patch proposal workers, Qwopus paths, Qwen3-Coder-Next experiments, or Ornith 9B
fallbacks; those details are historical unless the operator explicitly revives
them.

## Current Rule

Local workers are opt-in. Do not launch a local worker just because a task is
non-trivial, because a doc mentions scouts, or because an old plan used local
parallelism.

Deterministic Hermes tool lanes, such as parser/extractor/verifier scripts, are
not local model workers. Use those tool lanes for mechanical repo operations
before considering a model route.

Use a local worker only when:

- the operator explicitly asks for local-fleet/local-worker help;
- the active task/session explicitly selects a local worker; or
- a diagnostic, scout, builder, judge, or verification step requires one.

## Active Fleet

When local-worker use is opted in, use only the two-model active DevFlow fleet:

- **Ornith 35B on `8084`**: primary scout/builder/coder. It runs with `-np 3`,
  so one Ornith process can handle up to three parallel scout/builder requests.
- **Qwen 27B on `8083`**: dense thinking judge for review, validation, final
  approval, and strict-output checks. Parallel slots: 1.

**Swap rule:** Ornith 35B and Qwen 27B cannot run at the same time. The
model-router enforces one heavy process at a time. Run scout/build phases on
Ornith, then swap to Qwen only for judge/review phases.

`~/.hermes/scripts/model-router status` is informational, not gating. A model
showing `down` means it is not resident, not unavailable. Request the lane and
let the router handle start/stop/swap. Treat a lane as blocked only if the
router cannot start it or a real healthcheck/completion fails.

## Retired From Active DevFlow Use

These models/routes may still exist in config, old docs, or process state, but
they are not active DevFlow scout, builder, judge, UI, fallback, or emergency
lanes:

- Ornith 9B
- Qwopus 35B
- Qwen3-Coder-Next
- MLX/Ollama/Gemma legacy advisory paths
- legacy Dev-Flow local patch workers such as `qwopus-implementer`

## Supported Workflow

The supervisor stays lean and reads compact evidence, not raw logs or large
source files. Follow the scout-first workflow in
[docs/agent-operating-contract.md](agent-operating-contract.md):

1. Read the user prompt, named handoff/plan, and relevant skill.
2. Run scout/map/compression lanes to produce structured evidence.
3. Route deterministic work to deterministic tools first.
4. Route new code or ambiguous changes to Ornith builder/scout lanes.
5. Route review/judgment to Qwen after Ornith work completes.
6. Verify through `local_test_runner.py`.

## Codex / Hermes Surface Notes

In Codex sessions, use the visible subagent lane only when that surface is
configured for the current active fleet. Required proof is a spawned subagent's
output surfaced back into the parent session. Direct HTTP probes, MCP tests, and
`/v1/models` checks are diagnostic support, not worker-lane proof.

In Hermes sessions, use the fleet scripts and router described in
[docs/fleet-debrief.md](fleet-debrief.md). Worker output is evidence for the
supervisor to review, not final proof of completion.

If a worker surface is unavailable or rejects the custom agent, say that
explicitly before falling back to a narrower diagnostic or deterministic tool.

## Safety Invariants

- Run at most one heavy local model process at a time.
- Ornith 35B supports up to 3 parallel scout/builder jobs inside the one process.
- Qwen 27B is judge-only and runs one review at a time.
- Ornith and Qwen must not run simultaneously.
- `/v1/models` and open ports are not readiness proof; use a real completion.
- Worker output is evidence, not proof.
- The supervisor/main agent owns semantic review, final verification, and claims
  of completion.
- MCP fleet telemetry stays disabled unless the current session needs it.
- Active smoke completions are decision-point proof, not routine inventory.

## Compression Lane

Route large files and large command output through the local-fleet-efficiency
compression tools before reading them in frontier context. The active LLM-backed
compression/scout lane is Ornith 35B on `8084`.

Use:

```bash
python3 ~/.hermes/skills/software-development/local-fleet-efficiency/scripts/compress_tool_output.py
python3 ~/.hermes/skills/software-development/local-fleet-efficiency/scripts/extract_methods.py
python3 ~/.hermes/skills/software-development/local-fleet-efficiency/scripts/codebase_survey.py
```

## Current Authority Chain

Use this chain when docs disagree:

1. Current human instruction.
2. [docs/fleet-debrief.md](fleet-debrief.md) and
   [.devflow/fleet-contract.json](../.devflow/fleet-contract.json).
3. [AGENTS.md](../AGENTS.md) local worker policy.
4. This policy.
5. Historical plans, rollout docs, and older architecture notes.

Historical docs should preserve evidence, but they must not reintroduce retired
models, fallback routing menus, or automatic worker selection.
