# Fleet Routing Brief for Agent Sessions
## Last updated: 2026-07-06

## Fleet Configuration

One heavy model *process* runs at a time. The model-router handles swaps.
**Within Ornith 35B, 3 concurrent jobs can run in parallel** (`-np 3` slots).

| Port | Model | Role | Parallel | When to Use |
|---|---|---|---|---|
| 8084 | Ornith 35B (MoE, Q4) | Builder/coder/scout | **3 slots** | Code generation, extraction, refactoring, debugging, AST scans. 3B active, reasoning mode, self-scaffolding RL. Dispatch up to 3 concurrent jobs. |
| 8083 | Qwen 27B (Q5, MTP) | Judge | 1 | Code review, validation, final approval (thinking mode ON). Different model family — genuine second opinion. |
| 8085 | Ornith 9B (Q4) | Light fallback | 4 | Emergency compression/extraction only when 35B is down. |
| 8086 | Qwopus 35B (Q4) | Specialty | 1 | Emergency use only. |
| 8087 | Qwen3-Coder-Next (80B-A3B) | Specialty: security/math | 1 | Non-thinking. Lower agentic scores than Ornith 35B. Niche use only. |

**Parallel slot rule:** "One heavy model at a time" means one heavy *process*
running — not one *job*. Ornith 35B can handle 3 concurrent builder/scout jobs
through its parallel slots. Do not serialize work that could run in parallel.

## Key Rules

1. **Do NOT modify DevFlow source files when configuring models.** Model installation should only touch Hermes config, lifecycle scripts, profiles, Codex configs, and DevFlow registry/manifest files.

2. **Do NOT extract or refactor `local_ai_fleet.py` manually.** Use `extract_module.py` — it's deterministic and needs no LLM.

3. **Port assignments are stable:**
   - 8083 = Qwen 27B (judge)
   - 8084 = Ornith 35B (builder/scout)
   - 8085 = Ornith 9B (light fallback)
   - 8086 = Qwopus 35B (specialty)
   - 8087 = Qwen3-Coder-Next (specialty)

4. **Ornith 35B supports reasoning mode** (`` blocks). Its lifecycle script sets `enable_thinking=False` for compression jobs but can be enabled for complex reasoning tasks.

5. **Qwen 27B uses thinking mode for judging.** Different model family from Ornith — provides genuine second opinion.

6. **Qwen3-Coder-Next is non-thinking only.** Lower agentic scores than Ornith 35B. Only use for niche security review or math-heavy algorithmic tasks.

## Builder-Judge Workflow

```
1. Ornith 35B (8084) generates code (reasoning mode)
2. Router swaps to Qwen 27B (8083)
3. Qwen 27B reviews with thinking mode
4. If CHANGES_NEEDED: swap back to 8084, regenerate
5. If APPROVED: done
```

For module-level function extraction (DevFlow refactoring), use `extract_module.py` instead — deterministic, no LLM needed.
