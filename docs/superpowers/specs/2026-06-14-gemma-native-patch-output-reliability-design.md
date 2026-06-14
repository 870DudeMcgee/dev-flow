# Gemma Native Patch Output Reliability Design

## Goal

Make the registry-backed local Ollama patch worker produce usable structured patch proposal evidence with `gemma4:12b-it-qat`, without adding autonomous routing, hidden memory, Hermes-owned execution, or provider fallback.

## Trigger Evidence

Task 5B of Milestone 16 exposed a model-output reliability blocker, not a selection blocker:

- `task-0034` proved selection fails closed before a matching installed registry agent exists.
- Commit `d414ea00635e671aeb8468ca36b0b8a17445caad` added `gemma4-12b-qat-implementer` to `.devflow/agents/registry.yaml`.
- `task-0035` then selected `gemma4-12b-qat-implementer` for `implementation_worker`.
- `devflow task run task-0035 --worker gemma4-12b-qat-implementer` called local Ollama at `/api/generate`, but wrote only `{"` to `raw_output.md`.
- The recorded Ollama metadata showed `done_reason: length`, `prompt_eval_count: 4095`, and `eval_count: 1`.
- No `proposal.patch` was produced, so `task-0035` was closed `evidence-only`.

Direct local probes against the same installed model proved the model can produce valid JSON when generation settings are explicit:

- `/api/generate` with `format: "json"`, `num_ctx: 8192`, and `num_predict: 512` returned the requested JSON object.
- `/api/chat` with `think: false`, `num_ctx: 8192`, and `num_predict: 512` returned the requested JSON object in `message.content`.

The current `src/devflow/control_room/ollama_worker.py` patch path sends only:

```json
{
  "stream": false,
  "format": "json",
  "options": {
    "temperature": 0.2
  }
}
```

That explains the observed `done_reason: length` and one-token response.

## Product Decision

Fix the local patch adapter first. Do not move this problem into Hermes, memory, or tool access.

Dev-Flow should treat Gemma as a replaceable local patch worker only after it can reliably leave parseable, task-local evidence. Hermes can remain an operator/chat surface that calls supervisor-safe Dev-Flow commands, but Hermes must not own the worker run, bypass Dev-Flow evidence paths, provide hidden memory, apply patches, verify, promote, merge, or push.

## Non-Goals

- No autonomous model routing.
- No silent fallback from Gemma to another model.
- No Hermes worker/runtime adapter.
- No hidden model memory, embeddings, RAG, or training loop.
- No remote provider execution.
- No automatic patch application, verification, promotion, merge, push, or pull request creation.
- No broad benchmark harness before the narrow patch worker can complete one dogfood task.

## Architecture

Add a small generation-settings boundary for registry-backed local Ollama patch workers.

The boundary should be deterministic and local:

```text
AgentDefinition
-> OllamaPatchGenerationSettings
-> request builder for /api/generate or /api/chat
-> recorded request settings in run.json
-> parser diagnostics that explain length-truncated JSON
```

For `gemma4-12b-qat-implementer`, use native Ollama chat first:

- endpoint: `/api/chat`
- messages: system and user prompt
- `stream: false`
- `think: false`
- `format: "json"`
- `options.temperature: 0.2`
- `options.num_ctx: 8192`
- `options.num_predict: 4096`

For existing non-Gemma local patch workers, keep `/api/generate` but add explicit bounded generation options:

- endpoint: `/api/generate`
- `format: "json"`
- `options.temperature: 0.2`
- `options.num_ctx: 8192`
- `options.num_predict: 4096`

This keeps Qwopus behavior recognizable while removing the same class of implicit default risk.

## Evidence Contract

Every local patch run should record enough request metadata to debug model-output failures without leaking the full prompt into `run.json`:

- `request_endpoint`
- `request_payload_shape`
- `request_options`
- `request_format`
- `native_chat_think`
- `prompt_chars`
- `system_instruction_chars`
- `ollama_response.done_reason`
- `ollama_response.prompt_eval_count`
- `ollama_response.eval_count`

The raw model text remains in `raw_output.md`. The full prompt remains represented by existing packet/context artifacts, not duplicated into `run.json`.

## Failure Diagnostics

If parsing fails and Ollama reports `done_reason: length`, the worker result should say that local generation stopped before a complete JSON object was produced. If `eval_count <= 1`, include the stronger diagnostic that the model emitted only the JSON prefix or an equivalent one-token response.

The next suggested action stays an escalation packet or worker-settings fix. The worker must not retry with a different model inside `task run`.

## Hermes Position

Hermes can be useful after this slice, but only as an external operator gateway over explicit Dev-Flow commands such as:

```bash
devflow agent discover-local --json
devflow agent select-local <task_id> --role implementation_worker --json
devflow task show <task_id>
devflow task run <task_id> --worker gemma4-12b-qat-implementer
```

Hermes must not become the source of context, tools, memory, patch application, verification, promotion, or routing. Dev-Flow owns those artifacts and gates.

## Acceptance Criteria

- Focused tests prove the Gemma patch worker uses native Ollama chat with explicit `num_ctx`, `num_predict`, `temperature`, `think: false`, and JSON formatting.
- Focused tests prove existing non-Gemma local patch workers keep `/api/generate` but receive explicit bounded generation settings.
- `run.json` records endpoint and generation settings for local patch runs.
- Malformed JSON caused by `done_reason: length` gets a clear diagnostic in `run.json`, `result.md`, and `worker_failed.json`.
- A real dogfood rerun selects `gemma4-12b-qat-implementer` explicitly before `task run`.
- If the dogfood rerun produces `proposal.patch`, the normal review, dry-run, apply, verify, and review-ready ladder is used.
- If the dogfood rerun still fails, the task is closed `evidence-only` with recorded endpoint, options, raw output, and next safe action.
- Active docs remain clear that local patch workers only propose patches and Dev-Flow owns application, verification, and promotion.

## Likely Files

- `src/devflow/control_room/ollama_worker.py`
- `src/devflow/control_room/ollama_generation.py`
- `tests/test_ollama_worker.py`
- `docs/architecture/local-model-worker-pool.md`
- `docs/control-room-mvp.md`
- `docs/superpowers/plans/2026-06-13-milestone-16-agent-registry-runtime-hardening.md`
- `docs/handoffs/2026-06-14-gemma-native-patch-output-reliability-next.md`

## Self-Check

- This builds the Dev-Flow control room, not a new coding agent.
- Agents remain replaceable because settings are derived from registry agent metadata and model identity, not hidden chat state.
- State remains durable because evidence stays in task-local files.
- Failure remains safe because malformed output does not apply patches.
- The first fix is small enough to verify with mocks and one dogfood task.
- Hermes remains an operator gateway option, not an execution bypass.
