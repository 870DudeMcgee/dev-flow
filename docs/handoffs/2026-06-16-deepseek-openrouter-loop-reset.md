# DeepSeek/OpenRouter DevFlow Loop Handoff

Date: 2026-06-16
Status: resolved historical handoff
Repo: `/Users/jewelbait/Desktop/Local AI Dev Team`
Branch: `main`
Resolution commit: `21cbc31 fix: add minimal OpenRouter patch prompt mode`

## Status

complete

This handoff is retained as historical context for the DeepSeek/OpenRouter repair loop. Do not treat the old prompt-reduction plan as pending work; it was implemented and pushed in `21cbc31`.

## Files Changed

- `src/devflow/control_room/openrouter_agent.py`
  - Added `DEVFLOW_OPENROUTER_PATCH_PROMPT_MODE`.
  - Kept `standard` as the default TaskPacket/context-pack prompt path.
  - Added the opt-in `minimal` prompt path for tiny explicit patch proposals.
  - Recorded `prompt_mode` and `prompt_chars` in patch run evidence.
  - Disabled provider-side reasoning for minimal Flash patch proposals with `{"enabled": false, "exclude": true}`.
- `src/devflow/cli.py`
  - Shows patch prompt metadata in non-JSON output.
- `tests/test_openrouter_advisory.py`
  - Covers standard patch behavior, minimal prompt behavior, invalid prompt modes, and Flash/Pro registry patch profiles.
- `tests/test_agent_registry.py`
  - Covers registry/runtime visibility for OpenRouter patch profiles.
- `docs/control-room-mvp.md`
  - Documents registry-swappable OpenRouter patch profiles.
  - Documents the Hermes/OpenRouter env inheritance trap.
  - Documents why minimal Flash patch proposals must not use `reasoning.effort=minimal`.

## Verification

- `PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_openrouter_advisory.py tests/test_agent_registry.py -q`: pass, `32 passed`.
- `git diff --check`: pass.
- Direct real OpenRouter proof with `task-0023`: pass.
  - `prompt_mode: minimal`
  - `prompt_truncated: false`
  - `will_call_provider: true`
  - `reasoning_tokens: 0`
  - `proposal_patch_path: .devflow/tasks/task-0023/agents/deepseek-v4-flash-patch-proposer/proposal.patch`

## Risks

- Hermes may have `OPENROUTER_API_KEY` in `~/.hermes/.env` while Codex/Desktop subprocesses do not inherit it. For direct CLI proofs, load only the `OPENROUTER_API_KEY` value from `~/.hermes/.env`; do not source the whole file.
- DeepSeek Flash can spend the whole 2,048-token completion budget on hidden reasoning when `reasoning.effort=minimal` is sent with the patch prompt. Minimal patch mode intentionally sends `{"enabled": false, "exclude": true}` instead.
- The proof patch for `task-0023` was evidence only and was not applied.

## Next Safe Action

- Use `DEVFLOW_OPENROUTER_PATCH_PROMPT_MODE=minimal` for tiny explicit OpenRouter patch proposals, then continue through normal `review-patch`, `patch-dry-run`, `apply-patch`, verification, and promotion gates.
