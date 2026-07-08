# Local Worker Policy

Status: active pointer

The single source of truth for Codex session behavior, local-worker routing,
active fleet, Agent Proxy use, and freshness closeout is:

`/Users/jewelbait/.codex/session-operating-contract.md`

DevFlow-specific scripts
remain available where the contract or repo `AGENTS.md` routes to them:

```bash
python3 ~/.hermes/skills/software-development/local-fleet-efficiency/scripts/compress_tool_output.py
python3 ~/.hermes/skills/software-development/local-fleet-efficiency/scripts/extract_methods.py
python3 ~/.hermes/skills/software-development/local-fleet-efficiency/scripts/codebase_survey.py
```

## Active role mapping

The current local model role split is:

| Stage | Lane | Model | Port | Use |
|---|---|---|---:|---|
| Spec / planner / research scout | `local-agents-a1-q4` | Agents-A1 Q4_K_M | 8087 | Turn rough intent and evidence into bounded specs, planning packets, risks, and research synthesis. |
| Scout / builder / compression | `local-ornith-35b` | Ornith 35B | 8084 | Codebase survey, bounded implementation, code generation, and compact evidence synthesis. |
| Judge / validator | `local-llama-mtp` | Qwen 27B Q5 MTP | 8083 | Plan review, implementation judging, validation, and second opinion. |

Agents-A1 is not the primary coding builder. Use it before Ornith when the loop
needs a better spec or planning packet. Keep heavy-model residency explicit via
`~/.hermes/scripts/model-router`; the router owns swaps between lanes.

## Model evaluation posture

The previous repo-local model-tuning/scoring loop is retired. It produced noisy
comparisons because it used tiny prompts, circular model-as-its-own-judge
scoring, and single-run scores that did not match DevFlow's real
planner/builder/judge workload.

Current evaluation work should be ground-truth-first and role-specific:

- preserve raw run data under `.devflow/model-tuning-runs/` as historical evidence;
- evaluate planner, builder, and judge roles separately;
- use real DevFlow packets near the actual workload size for each role;
- compare candidates against an incumbent and a known-good/known-bad ground-truth set;
- treat Qwen 27B Q5 MTP on `local-llama-mtp` as the incumbent judge until better evidence exists;
- do not promote a model from a single score, self-judged result, or synthetic micro-prompt.

If a new scoring loop is added, it should land as normal DevFlow source/tests
with explicit ground-truth fixtures and deterministic verification before any
model-role routing changes are made.
