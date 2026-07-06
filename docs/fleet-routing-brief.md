# Fleet Routing Brief for Agent Sessions
## Last updated: 2026-07-06

## Fleet Configuration

| Port | Model | Role | When to Use |
|---|---|---|---|
| Ornith 35B (MoE, Q4) | 8084 | Builder/coder/scout | Code generation, extraction, refactoring, debugging, AST scans. 3B active, reasoning mode, `-np 3` (3 parallel slots). |
| Qwen 27B (Q5, MTP) | 8083 | Judge | Code review, validation, final approval (thinking mode ON). Different model family — genuine second opinion. |
| Ornith 9B (Q4) | 8085 | Light fallback | Emergency compression/extraction only when 35B is down. |
| Qwopus 35B (Q4) | 8086 | Specialty fallback | Emergency use only. |
| Qwen3-Coder-Next (80B-A3B, IQ4_XS) | 8087 | Specialty: security/math | Non-thinking mode. Lower agentic scores than Ornith 35B. Use only for niche security review or math-heavy tasks. |

**One heavy model at a time.** The model-router handles starts/stops/swaps automatically. Do NOT manually start or stop models — use `~/.hermes/scripts/model-router start <name>` and let it manage the swap.

**Ornith 35B is the primary builder.** It outperforms Qwen3-Coder-Next on every agentic coding benchmark (SWE-Bench 75.6 vs 70.6, Terminal-Bench 64.2 vs 34.2) and has reasoning mode. Do not replace it with Qwen3-Coder-Next for general coding work.

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
