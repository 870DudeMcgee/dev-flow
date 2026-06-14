# Gemma Native Patch Output Reliability Next Handoff

## Status

needs-review

## Files Changed

- `docs/superpowers/specs/2026-06-14-gemma-native-patch-output-reliability-design.md` (new design spec for the Gemma local Ollama patch-output blocker)
- `docs/superpowers/plans/2026-06-14-gemma-native-patch-output-reliability.md` (new task-by-task implementation plan)
- `docs/handoffs/2026-06-14-gemma-native-patch-output-reliability-next.md` (this handoff)

## Verification

- `rg -n "T[B]D|T[O]DO|implement[ ]later|fill[ ]in[ ]details|Similar[ ]to[ ]Task|appropriate[ ]error[ ]handling|Write[ ]tests[ ]for[ ]the[ ]above|place[ ]holder" docs/superpowers/specs/2026-06-14-gemma-native-patch-output-reliability-design.md docs/superpowers/plans/2026-06-14-gemma-native-patch-output-reliability.md docs/handoffs/2026-06-14-gemma-native-patch-output-reliability-next.md -S`: pass, no matches
- `git diff --check`: pass, no output
- `task-0035` evidence inspected: selected `gemma4-12b-qat-implementer`, then local Ollama returned raw output `{"`, `done_reason: length`, `prompt_eval_count: 4095`, `eval_count: 1`, and no `proposal.patch`.
- Direct local probes before this handoff: `gemma4:12b-it-qat` returned valid JSON through `/api/generate` and `/api/chat` when `num_ctx` and `num_predict` were explicit.
- Current Git state before this docs slice: clean `main`, ahead `1`, behind `0`; unpushed head `d414ea00635e671aeb8468ca36b0b8a17445caad` contains the registry entry for `gemma4-12b-qat-implementer`.

## Risks

- The registry commit is not pushed yet. After checkpointing this docs slice, local `main` will have both the registry commit and the planning commit ahead of origin until `push-main` runs.
- Task 5B dogfood is blocked until the local Ollama patch worker uses explicit Gemma generation settings and records them in evidence.
- Hermes should not be introduced as a runtime bypass. Keep Hermes limited to operator-safe Dev-Flow commands unless a separate design promotes more behavior.

## Next Safe Action

- Run `PYTHONPATH=src:. .venv/bin/devflow push-main`.
