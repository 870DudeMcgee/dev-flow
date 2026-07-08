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

## Actual-model quality scoring loop

Use the repo-local scoring loop when the question is whether the active
Agents-A1/Ornith/Qwen chain is producing dense, grounded, role-appropriate
output rather than merely returning syntactically valid responses.

```bash
python scripts/model_quality_scoring_loop.py \
  --evidence-dir .devflow/evidence/<actual-e2e-run-id> \
  --threshold 9.5 \
  --max-iterations 3
```

The loop writes prompts, raw responses, scorecards, and run metadata under
`.devflow/model-quality-runs/<run-id>/`. It starts the configured builder lane
first (`local-ornith-35b`), swaps to the judge lane (`local-llama-mtp`), and
feeds judge feedback back into the next builder iteration until the score meets
the threshold or the iteration budget is exhausted.

Scoring dimensions are:

- format compliance
- grounding to evidence
- role specificity
- density
- actionability
- adversarial review
- absence of weird or unsupported output

Treat a score below 9.5 as useful evidence, not success. Improve the packet,
prompt, schema, or model role contract and rerun the loop until every model in
the chain produces high-density, evidence-cited output for its role.