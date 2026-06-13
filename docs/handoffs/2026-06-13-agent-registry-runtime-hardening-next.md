# Milestone 16 Agent Registry Runtime Hardening Next Handoff

## Status

needs-review

## Files Changed

- `docs/roadmap.md` (marked Milestone 15/15B implemented and added Milestone 16 as the next planned slice)
- `docs/control-room-mvp.md` (updated current-priority callout and adapter-runtime boundary wording)
- `docs/mvp-contract.md` (updated current-priority callout)
- `CODE_MAP.md` (clarified that Milestone 16 promotes registry runtime hardening only, not remote provider execution)
- `docs/superpowers/specs/2026-06-13-milestone-16-agent-registry-runtime-hardening-design.md` (new design spec)
- `docs/superpowers/plans/2026-06-13-milestone-16-agent-registry-runtime-hardening.md` (new implementation plan)
- `docs/handoffs/2026-06-13-agent-registry-runtime-hardening-next.md` (this handoff)

## Verification

- `PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_workflow_orchestration_docs.py tests/test_project_scope_docs.py tests/test_devmode_contract.py tests/test_release_readiness.py -q`: pass, `24 passed`
- `git diff --check`: pass, no output
- `rg -n "TBD|TODO|implement later|fill in details|Similar to Task|appropriate error handling|Write tests for the above" docs/superpowers/specs/2026-06-13-milestone-16-agent-registry-runtime-hardening-design.md docs/superpowers/plans/2026-06-13-milestone-16-agent-registry-runtime-hardening.md -S`: pass, no matches
- `rg -n "Status: next planned slice\.|Start the Milestone 15 spec|Milestone 15 set as the next planned|Milestone 15B.*run the first mutation|Current Priority.*next planned slice is multi-project|currently enables remote provider|remote provider execution is stable|provider-backed.*current stable|autonomous routing.*current behavior" README.md PRODUCT_NORTH_STAR.md CODE_MAP.md docs/control-room-mvp.md docs/mvp-contract.md docs/roadmap.md docs/architecture docs/handoffs --glob '!docs/handoffs/2026-06-13-agent-registry-runtime-hardening-next.md' -S`: pass, no matches
- `PYTHONPATH=src:. .venv/bin/devflow map check`: pass, `CODE_MAP.md check passed`
- `PYTHONPATH=src:. .venv/bin/devflow git status`: pass, dirty only from this docs/spec/plan/handoff slice; ahead `0`, behind `0`

## Risks

- Milestone 16 must harden existing local/manual/shell/local-patch runtime seams only. It must not enable remote provider task execution, autonomous routing, PR automation, database state, hidden memory, or worker-owned verification/promotion.
- The implementation plan includes local Ollama dogfood only when local Ollama is available; if unavailable, the next agent should record the blocker rather than fabricating model evidence.
- The source repo is intentionally dirty until this docs handoff slice is checkpointed.

## Next Safe Action

- If approved, run `PYTHONPATH=src:. .venv/bin/devflow git checkpoint --message "docs: plan milestone 16 agent registry runtime" --yes`, then start Task 1 in `docs/superpowers/plans/2026-06-13-milestone-16-agent-registry-runtime-hardening.md`.
