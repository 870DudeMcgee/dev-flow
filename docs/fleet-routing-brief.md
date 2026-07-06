# Fleet Routing Brief for Agent Sessions

Last updated: 2026-07-06
Authority: [docs/fleet-debrief.md](fleet-debrief.md), [.devflow/fleet-contract.json](../.devflow/fleet-contract.json)

## Active Fleet Configuration

One heavy model **process** runs at a time. The model-router handles swaps.
Within Ornith 35B, up to 3 concurrent scout/builder jobs can run in parallel
through the single `-np 3` process.

| Port | Model | Role | Parallel | When to Use |
|---|---|---:|---:|---|
| 8084 | Ornith 35B (MoE, Q4) | Builder/coder/scout | **3 slots** | Code generation, refactoring, debugging, codebase surveys, compression, AST/file inspection when LLM comprehension is needed. |
| 8083 | Qwen 27B (Q5, MTP) | Judge | 1 | Code review, validation, final approval, strict-output checks, architecture judgment. |

## Swap Rule

**Ornith 35B and Qwen 27B cannot run at the same time.**

- Run scout/build phases on Ornith 35B.
- Use up to 3 parallel Ornith scout/builder requests when work is independent.
- Swap to Qwen 27B only for judge/review phases.
- Do not start Qwen while Ornith jobs are still running.

`model-router status` is informational. A model showing `down` is not a lane
outage; it only means the process is not resident. Request the lane and let the
router start/stop/swap. Treat a lane as blocked only if the router cannot start
it or a real completion/healthcheck fails after start.

## Retired From Active DevFlow Use

The following may still appear in old docs, local config, or process state, but
must not be used as active DevFlow scout, builder, judge, UI, fallback, or
emergency lanes:

- Ornith 9B
- Qwopus 35B
- Qwen3-Coder-Next

## Key Rules

1. **Do NOT modify DevFlow source files when configuring models.** Model
   installation should only touch Hermes config, lifecycle scripts, profiles,
   Codex configs, and DevFlow registry/manifest files.
2. **Tool-first for mechanical operations.** If a deterministic script can do the
   work exactly, use it before a model lane.
3. **Ornith 35B supports reasoning mode** and has self-scaffolding RL behavior;
   it is the primary scout/builder.
4. **Qwen 27B uses thinking mode for judging** and provides a dense-model second
   opinion.
5. **Do not resurrect retired models** from historical docs or stale handoffs.

## Builder-Judge Workflow

```text
1. Ornith 35B (8084) generates or scouts while other Ornith jobs may run, up to 3 slots.
2. Wait for Ornith jobs to complete.
3. Router swaps to Qwen 27B (8083).
4. Qwen 27B reviews with thinking mode.
5. If CHANGES_NEEDED: swap back to Ornith 35B for the next build pass.
6. If APPROVED: proceed to deterministic verification.
```

For module-level function extraction, use `extract_module.py` instead — it is
deterministic and needs no LLM.
