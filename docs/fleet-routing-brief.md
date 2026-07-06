# Fleet Routing Brief for Codex Sessions
## Last updated: 2026-07-06

## Fleet Configuration

| Model | Port | Group | Role | When to Use |
|---|---|---|---|---|
| Qwen3-Coder-Next (80B-A3B, IQ4_XS) | 8084 | heavy | Builder/Coder | Code generation, extraction, refactoring, debugging |
| Qwen 27B (Q5, MTP) | 8083 | heavy | Judge | Code review, validation, final approval (thinking mode ON) |
| Ornith 35B (Q4) | 8086 | heavy | Scout | AST scanning, file inspection, deterministic scouts |

**One heavy model at a time.** The model-router handles starts/stops/swaps automatically. Do NOT manually start or stop models — use `~/.hermes/scripts/model-router start <name>` and let it manage the swap.

## Key Rules

1. **Do NOT modify DevFlow source files when configuring models.** Model installation should only touch:
   - `~/.hermes/config.yaml`
   - `~/.hermes/scripts/*-lifecycle.sh`
   - `~/.hermes/profiles/*/config.yaml`
   - `~/.codex/` config files
   - DevFlow's `.devflow/providers/` and `.devflow/agents/` registry files
   - DevFlow's `src/devflow/control_room/data/local_model_expected_profiles.yaml` (manifest only)

2. **Do NOT extract or refactor `local_ai_fleet.py`.** That work is managed by the `extract_module.py` tool in `~/.hermes/skills/software-development/local-fleet-efficiency/scripts/`. Codex sessions should not perform module decomposition — that's a deterministic tool job, not a coding agent job.

3. **Port assignments are final:**
   - 8083 = Qwen 27B (judge)
   - 8084 = Qwen3-Coder-Next (builder)
   - 8086 = Ornith 35B (scout)
   - 8081/8082 = MLX (fallback, not primary)
   - 8085 = retired (was Ornith 9B)
   - 8087 = retired (was temp Qwen3-Coder-Next before move to 8084)

4. **Qwen3-Coder-Next is non-thinking mode only.** It does NOT generate `<think>` blocks. Do not set `enable_thinking=True` for this model.

5. **Qwen 27B uses thinking mode for judging.** Its lifecycle script should set `enable_thinking=True` or use the appropriate chat template.

6. **Ornith 35B is a scout, not a builder.** Use it for deterministic AST scans, file surveys, and codebase orientation — NOT for code generation.

## Builder-Judge Workflow

```
1. Qwen3-Coder-Next (8084) generates code
2. Router swaps to Qwen 27B (8083)
3. Qwen 27B reviews with thinking mode
4. If CHANGES_NEEDED: swap back to 8084, regenerate
5. If APPROVED: done
```

For module-level function extraction (DevFlow refactoring), use `extract_module.py` instead of the builder-judge loop — it's deterministic and needs no model.

## DevFlow Manifest

The model manifest at `src/devflow/control_room/data/local_model_expected_profiles.yaml` should list:
- `hermes-qwen3-coder-next` as the supervisor/builder profile
- `hermes-qwen36-27b-q5-mtp` as the judge profile
- `hermes-ornith-35b` as the scout profile (if DevFlow uses it for readiness checks)

## What Codex Should NOT Do

- Do not modify `local_ai_fleet.py`, `local_model_server.py`, `local_model_readiness.py`, or `hermes_profile_resolver.py` during model installation
- Do not create new Python modules in `src/devflow/control_room/` for model wiring
- Do not run builder-judge loops for verbatim code extraction — use `extract_module.py`
- Do not start models on ports other than those listed above
- Do not set `enable_thinking=True` for Qwen3-Coder-Next
- Do not retire Qwen 27B — it is the judge, not a fallback
- Do not retire Ornith 35B — it is the scout, not a deprecated model
