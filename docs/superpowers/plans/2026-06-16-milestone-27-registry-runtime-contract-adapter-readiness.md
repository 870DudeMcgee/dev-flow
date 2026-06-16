# Milestone 27 Registry Runtime Contract / Adapter Readiness Plan

Status: implemented and verified locally on 2026-06-16.

> For agentic workers: keep active product logic under `src/devflow/control_room/`; top-level CLI edits may only present control-room projections.

**Goal:** Make the existing agent registry/runtime surfaces explicit about what can execute, what can only write evidence, what is packet-only/read-only, and why provider-backed agents are refused, without enabling provider execution or autonomous routing.

**Checkpoint:** Milestone 26 baseline was checkpointed first with `devflow git checkpoint --message "chore: checkpoint milestone 26 operational baseline" --yes`.

## Guardrails

- Do not enable provider-backed adapters, autonomous routing, scheduler expansion, auto-resume, auto-promotion, commits, pushes, PRs, databases, RAG, embeddings, or hidden memory.
- Preserve `devflow task run <task_id> --worker shell -- <command>` as the preferred daily shell command.
- Add `devflow-shell-worker` as a registry-visible shell alias that still runs only inside the isolated task workspace and writes Dev-Flow-owned evidence under the task agent directory.
- Keep runtime/refusal policy in `src/devflow/control_room/`.
- Keep `src/devflow/cli.py` a thin presenter over control-room payloads.

## Tasks

- [x] Extend the runtime projection with a stable JSON `runtime_contract` payload and scan-friendly text summaries.
- [x] Add builtin `devflow-shell-worker` with shell workspace boundaries and evidence requirements.
- [x] Include runtime contract data in `agent list --json`, `agent show --json`, and `agent packet`.
- [x] Ensure frontier/provider-backed read-only agents remain non-executable through `task run` while still permitting local packets when their permission mode allows it.
- [x] Add production-readiness dogfood case `registry-runtime-contract`.
- [x] Add/extend focused tests for registry, runtime, CLI JSON/text, manual/shell packets, shell alias execution, remote refusal, and dogfood summary evidence.
- [x] Run the requested focused pytest command, `git diff --check`, and production-readiness dogfood.

## Verification Plan

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest \
  tests/test_agent_registry.py \
  tests/test_agent_runtime.py \
  tests/test_agent_local_worker_pool_cli.py \
  tests/test_manual_proof_agent.py \
  tests/test_dogfood_harness.py -q

git diff --check
PYTHONPATH=src:. .venv/bin/python -m devflow.cli dogfood run --suite production-readiness
```

Full pytest remains out of scope unless the implementation unexpectedly touches broad task lifecycle behavior.

## Verification Evidence

- `PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_agent_registry.py tests/test_agent_runtime.py tests/test_agent_local_worker_pool_cli.py tests/test_manual_proof_agent.py tests/test_dogfood_harness.py -q`: passed, `64 passed in 44.29s`.
- `git diff --check`: passed.
- `PYTHONPATH=src:. .venv/bin/python -m devflow.cli dogfood run --suite production-readiness`: passed, `score: 172/174`, `threshold: Bulletproof candidate`, `silver_met: yes`; warning retained from existing conservative `parallelism-decision-docs-test-split` guardrail.
