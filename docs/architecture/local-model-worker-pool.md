# Local Model Worker Pool

Status: active MVP wiring for registry-backed local worker-pool evidence plus small explicit local-model discovery and selection evidence. This is not a profiler, benchmark harness, second registry, Docker runtime, remote provider runtime, autonomous router, or promotion system.

## Purpose

Dev-Flow already has the important control-room pieces: `agent_registry.py`, `task_packet.py`, `local_packet_worker.py`, `local_model_client.py`, `qwopus_evidence.py`, supervisor surfaces, and Hermes operator docs. This milestone wires those pieces into practical use:

```text
agent_registry.py
-> starter local model profiles
-> bounded TaskPacket
-> local_model_client.py
-> WorkerEvidence
-> Hermes-readable CLI/status output
-> real task evidence improves later route-quality analysis
```

Dev-Flow owns state, verification, evidence, worker isolation, and promotion. Local workers produce evidence, not truth. Hermes may request eligible workers through the operator layer, but Hermes must not own worker state, bypass Dev-Flow, or mutate the repo directly.

## Existing Boundaries

- `agent_registry.py` is the source of truth for worker definitions, permissions, model allocation metadata, and Hermes delegation eligibility.
- `task_packet.py` is the bounded input mechanism. Worker prompts use rendered task packets rather than unbounded repo context.
- `local_packet_worker.py` remains the older advisory packet-review helper.
- `local_model_client.py` is the local model HTTP boundary. Dev-Flow must not load model weights or import heavy ML runtimes.
- `local_agent_discovery.py` is the explicit Ollama inventory, manifest parsing, deterministic capability classification, and selected-agent evidence boundary.
- `WorkerEvidence` is the generic bounded output/evidence mechanism for worker-pool runs.
- `QwopusEvidence` stays intact for the existing `qwopus-implementer` patch proposal path.
- Human approval controls patch application, verification, promotion, merges, and pushes.

Worker outputs are evidence. They can suggest next actions, risks, quality notes, or routing hints, but they do not prove correctness or readiness.

## Heterogeneous Local Fleet

Dev-Flow should model Josh's local models as a heterogeneous fleet, not one interchangeable machine.

### Mac Mini Small-Worker Class

| Model | Role name | Machine class | Weight | Primary role | Secondary roles | Use caution | Verify |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `gemma4:latest` | `gemma-fast-reviewer` | `mac_mini` | `small` | fast reviewer/summarizer | mini multimodal reviewer, evidence brief writer, docs reviewer | Josh's manifest identifies this as 8.0B Q4_K_M; do not confuse it with `gemma4:31b` | `ollama show gemma4:latest` |
| `qwen2.5-coder:7b-instruct` | `qwen-coder-fast` | `mac_mini` | `small` | small code helper | syntax fixes, small tests, simple implementation loops | keep to small isolated work and low-risk help until evidence proves more | `ollama show qwen2.5-coder:7b-instruct` |
| `qwen2.5-coder:1.5b` | `qwen-coder-tiny` | `mac_mini` | `tiny` | classifier/router utility | short summaries, labels, extraction, filenames/titles | do not ask it to judge complex code correctness | `ollama show qwen2.5-coder:1.5b` |

`gemma4:latest` manifest facts from Josh's latest local evidence: architecture `gemma4`, 8.0B parameters, context length 131072, embedding length 2560, Q4_K_M quantization, Apache 2.0 license, and capabilities including completion, vision, audio, tools, and thinking.

### Either Or Configurable

| Model | Role name | Machine class | Weight | Primary role | Secondary roles | Use caution | Verify |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `qwen2.5-coder:14b` | `qwen-coder-medium` | `either` | `medium` | medium implementation/test planning | code review, smaller debugging, test planning | may run on Mac mini only if observed performance is acceptable; do not assume it is a Mac mini default | `ollama show qwen2.5-coder:14b` |

### Mac Studio Heavy-Worker Class

| Model | Role name | Machine class | Weight | Primary role | Secondary roles | Use caution | Verify |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `qwopus:latest` | `qwopus-supervisor` | `mac_studio` | `heavy` | local supervisor/planner/repo reasoner | architecture review, risk review, task decomposition, deep debugging | likely alias of `qwen3.6:latest` until manifests prove otherwise | `ollama show qwopus:latest` |
| `qwen3.6:latest` | `qwen-local-supervisor` | `mac_studio` | `heavy` | local supervisor/planner/repo reasoner | architecture review, risk review, task decomposition, deep debugging | currently shows same Ollama ID as `qwopus:latest` in Josh's list | `ollama show qwen3.6:latest` |
| `qwen2.5-coder:32b-instruct` | `qwen-coder-heavy` | `mac_studio` | `heavy` | heavy local coding specialist | larger refactors, multi-file code generation, debugging, tests | any patch path must still go through existing proposal/review/dry-run/apply gates | `ollama show qwen2.5-coder:32b-instruct` |
| `gemma4-review:latest` (alias of `gemma4:31b`) | `gemma-dense-judge` | `mac_studio` | `heavy` | strict local reviewer/final judge | instruction-following audit, UX/spec verification, multimodal artifact review if manifest supports it | use as judge/reviewer, not a default implementation worker; preserve the operator's large local context window on capable machines | `ollama show gemma4-review:latest` |

Public model context can inform starter assumptions, but it is not authority. Google/Ollama list Gemma 4 tags including `gemma4:26b` and `gemma4:31b`; `gemma4:31b` is the dense 31B model and `gemma4:26b` is the 26B A4B MoE variant. The local dense-judge profile routes through `gemma4-review:latest`, a tuned alias of `gemma4:31b` that should preserve the operator's large local context window (for example `num_ctx 262144` when the local machine supports it). Model names are never enough: Dev-Flow should prefer actual `ollama show` manifests whenever available.

Identical Ollama IDs must be flagged as aliases or duplicate tags until `ollama show` proves different templates, parameters, or manifests.

## Starter Profiles

Current starter profiles are registry entries, not a second config file:

- `hermes-qwen36-27b-q5-mtp`
- `local-gemma4-qat`
- `local-qwen25-coder-14b`

The registry records model name, capability metadata, machine class, weight class, role name, secondary roles, caution notes, required verification command, and alias group when relevant. The editable operator surface remains the agent registry; do not add `config/local_workers.yaml` or a second registry.

Operator reviewer guidance:

- Prefer `local-gemma4-qat` when long context, screenshot/vision evidence, or broad local review matters.
- Use `local-qwen25-coder-14b` as the retained installed code-specialist fallback.
- Use `hermes-qwen36-27b-q5-mtp` for fast text/status/planning/operator loops when the local OpenAI-compatible server is active.
- Keep this as operator guidance only. It does not update routing policy, auto-select workers, apply patches, verify, promote, commit, merge, push, or bypass fresh audition evidence when model manifests or task shape change.

Conservative defaults:

- no promotion
- no commit, merge, or push
- no direct source edits
- no workspace writes for read-only worker-pool profiles
- no `proposal.patch` writes for read-only worker-pool profiles
- no arbitrary external network access
- local endpoint access only through `local_model_client.py`
- WorkerEvidence writes only under `.devflow/tasks/<task-id>/local-model-runs/<run-id>/`
- the quarantined `/Users/jewelbait/Desktop/DevFlow` path is forbidden

## CLI Slice

JSON surfaces for Hermes/supervisor use:

```bash
PYTHONPATH=src .venv/bin/python -m devflow.cli agent list --json
PYTHONPATH=src .venv/bin/python -m devflow.cli agent show local-gemma4-qat --json
PYTHONPATH=src .venv/bin/python -m devflow.cli agent policy --json
PYTHONPATH=src .venv/bin/python -m devflow.cli agent catalog --provider ollama --json
PYTHONPATH=src .venv/bin/python -m devflow.cli agent add-model --provider ollama --model <model-id> --authority read-only --role local_senior_worker --dry-run --json
PYTHONPATH=src .venv/bin/python -m devflow.cli agent add-model --provider ollama --model <model-id> --authority patch-proposer --role implementation_worker --json
PYTHONPATH=src .venv/bin/python -m devflow.cli agent discover-local --json
PYTHONPATH=src .venv/bin/python -m devflow.cli agent select-local <task-id> --role implementation_worker --json
PYTHONPATH=src .venv/bin/python -m devflow.cli agent audition <task-id> --job review-debug --dry-run --json
PYTHONPATH=src .venv/bin/python -m devflow.cli agent audition <task-id> --job review-debug --execute --json
PYTHONPATH=src .venv/bin/python -m devflow.cli agent run --task <task-id> --profile local-gemma4-qat --dry-run --json
PYTHONPATH=src .venv/bin/python -m devflow.cli agent run --task <task-id> --profile local-gemma4-qat --json
```

`agent catalog --provider ollama --json` is the read-only inventory surface for local model onboarding. It shows configured Ollama provider settings, registered profiles, runtime contracts, missing env vars, installed local Ollama models, manifests when `ollama show` is available, and unregistered installed models.

`agent add-model --provider ollama ...` is the supported way to turn an installed local model into a registry profile. `--authority read-only` generates a WorkerEvidence-only profile for `agent run`; `--authority patch-proposer` generates a local `proposal.patch` evidence surface for the existing patch review/dry-run/apply gates. Normal model profiles should stay named after the model/capability route. It writes/upserts `.devflow/agents/registry.yaml` from safe templates and refuses unknown roles, unsafe profile ids, duplicate conflicting profiles, and unsupported provider/authority combinations.

`agent discover-local` calls local Ollama only. It parses `ollama list`, calls `ollama show` for installed models, records manifest facts, and derives conservative capability profiles such as summarizer, reviewer, bounded worker, or patch-proposer candidate. Public model-name assumptions are advisory only; actual local manifests win.

`agent select-local <task-id> --role <role> --json` ranks installed registry agents for the requested role and writes `.devflow/tasks/<task-id>/agent-selection.json`. It does not run a worker, edit source, apply patches, verify, promote, or silently fall back to another model. Installed models that are not represented by a registry agent are reported as unregistered local models; they are not executable through `task run` or `agent run` until explicit `agent add-model` grants the needed permission surface.

Dry-run does not call the model and does not write evidence. It reports task id, profile id, model, adapter, runtime, maturity, permission mode, Hermes delegation, machine class, weight class, packet sizing, expected evidence paths, safety warnings, and mutation refusals.

`agent audition <task-id> --job <job-type> --dry-run --json` writes task-local audition planning evidence under `.devflow/tasks/<task-id>/model-auditions/dry-run-<job-type>/plan.json`. It selects up to three installed, read-only local worker-pool profiles for the requested job type, rejects unsafe or uninstalled profiles with reasons, and does not call models.

`agent audition <task-id> --job <job-type> --execute --json` requires worker-safe Git state, reuses or creates the dry-run plan, runs selected profiles sequentially through `run_local_model_profile`, and writes derived audition `plan.json`, `runs.json`, `scorecard.json`, and `report.md` under `.devflow/tasks/<task-id>/model-auditions/execute-<job-type>/`. The underlying model outputs remain normal WorkerEvidence under `local-model-runs`.

The real MVP vertical slice runs one safe local profile such as `local-gemma4-qat` or `local-qwen25-coder-14b`: it builds a bounded task packet, calls `LocalModelClient`, writes WorkerEvidence, caps raw output, captures failure, and stops. It does not edit source files, write `proposal.patch`, apply patches, verify, commit, merge, push, or promote.

`local-gemma4-qat` uses a Gemma-specific native Ollama chat path because Gemma 4 has thinking and vision capability and the OpenAI-compatible endpoint can cap or reshape full task packets in ways that hide the useful final content. That profile calls `/api/chat` with `think: false`, explicit `num_ctx`, and a compact evidence-summary packet. The quality gate still rejects missing task grounding, placeholder task ids, and generic readiness summaries.

`gemma4-12b-qat-implementer` is the first Gemma local patch runtime profile. It uses native Ollama `/api/chat` with thinking disabled and explicit bounded generation settings (`num_ctx 262144`, `num_predict 4096`) so patch proposal output is parseable JSON evidence without collapsing the input window to 8K. It still only writes `proposal.patch`, `raw_output.md`, `result.md`, `run.json`, logs, questions, or worker failure evidence under the task-local agent directory; Dev-Flow still owns patch review, dry-run, application, verification, and promotion.

## WorkerEvidence

WorkerEvidence stores:

- `worker_type`
- `profile_id` / `worker_id`
- `task_id`
- `task_path`
- `run_id`
- `evidence_dir`
- `run_metadata_path`
- `raw_output_path`
- `response_path`
- `packet_path`
- `error_path`
- `run_metadata`
- `model`
- `adapter` / `runtime`
- `adapter_maturity`
- `permission_mode`
- `hermes_delegable`
- machine and weight allocation metadata
- optional `quality_notes`
- optional `quality_score`
- capped raw output
- failure capture

Quality notes and scores are routing hints only. They are not truth, verification, or promotion readiness.

## Dogfood Refinement

No separate benchmark harness is required for this milestone. Refinement should come from real Dev-Flow work:

1. Run workers on actual tasks.
2. Inspect WorkerEvidence, task outcome, verification, and human review.
3. Adjust profile roles, prompts, machine assignments, and permissions.
4. Record good/bad output as route-quality evidence.
5. Keep human approval in front of patch application and promotion.

## Manifest Capture Workflow

Capture manifests as operator evidence when model facts matter:

```bash
mkdir -p .devflow/local-models/manifests
ollama show <model> > .devflow/local-models/manifests/<safe-model-name>.txt
```

Use safe filenames such as `qwopus-latest.txt`, `qwen3-6-latest.txt`, `qwen2-5-coder-32b-instruct.txt`, or `gemma4-31b.txt`.

This is a documented workflow, not a required runtime dependency. A future structured command may parse and store manifest fields, but the MVP should not block practical use behind model discovery or benchmarking.

## Future Docker-Isolated Worker Runtime

Docker is a wise future isolation layer for tool-using agents, but it is not active runtime in this milestone and must not become a required dependency.

A future Docker worker design should use:

- ephemeral containers
- read-only source mounts by default
- no secret mounts by default
- no network by default
- `cap-drop=ALL`
- bounded runtime and logs
- explicit output directories controlled by Dev-Flow
- WorkerEvidence as the only accepted result path

Do not add active Docker execution until the current registry, packet, evidence, verification, and promotion contracts are proven.
