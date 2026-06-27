# Dev-Flow Control-Room MVP

Date: 2026-05-27
Status: Active source of truth

## Current State

Dev-Flow is now a nearly production-shaped local operating layer, not a speculative swarm framework. The current work is about making the browser control room obvious, trustworthy, and useful enough that the operator does not have to babysit every small step.

The first screen should help the operator answer these questions without opening random logs:

- What tasks exist right now?
- Which ones are active, blocked, failed, verified, promoted, or closed?
- Which worker or model is attached to each task?
- What did that worker actually do?
- What is the next safe action?
- Which controls are available now: start, inspect, verify, retry, close, cleanup, or promote?

The canonical browser UI is `devflow operating-layer serve`. It must use the Python-bundled operating-layer files under `src/devflow/control_room/`, not the old static `public/` surface.

Use this module entrypoint when the console script is unavailable:

```bash
env PYTHONPATH=src:. .venv/bin/python -m devflow.cli operating-layer serve
```

## How To Read This Doc

This document is the near-term product authority. Read the top sections for current behavior and UX expectations. Treat the long command lists and milestone history below as reference material, not startup ceremony.

Use related docs only when needed:

- Operator-centered mission: [docs/operator-centered-mission.md](operator-centered-mission.md)
- Product direction: [PRODUCT_NORTH_STAR.md](../PRODUCT_NORTH_STAR.md)
- Runtime command/filesystem contract: [docs/mvp-contract.md](mvp-contract.md)
- Operating-layer UI architecture: [docs/architecture/local-operating-layer-ui.md](architecture/local-operating-layer-ui.md)
- Current operating-layer UI deepening backlog: [docs/architecture/operating-layer-ui-deepening-backlog.md](architecture/operating-layer-ui-deepening-backlog.md)
- Future registry/adapter roadmap: [docs/architecture/agent-registry-and-adapter-runtime.md](architecture/agent-registry-and-adapter-runtime.md)
- Future/evidence-only routing roadmap: [docs/architecture/agent-selection-and-context-routing.md](architecture/agent-selection-and-context-routing.md)
- Verification reuse: [docs/verification-ledger.md](verification-ledger.md)

Architecture documents are valuable, but they are not automatically active runtime behavior. If an architecture doc describes a future worker, model router, provider adapter, or autonomy policy, preserve it as roadmap context until a later implementation explicitly promotes it.

Hyperplane is currently quarantined as experimental evidence infrastructure. It is not an active first-pass model validation path and must not be used as a fail-fast smoke test. Its stock pipeline can expand a small-looking run into many generator, target, and judge calls; use direct bounded target/judge smoke evidence instead until a later task explicitly reopens Hyperplane.

Graphify is the current generated architecture baseline for cleanup decisions. Use [docs/architecture/graphify-architecture-baseline.md](architecture/graphify-architecture-baseline.md), `graphify-out/GRAPH_REPORT.md`, and `graphify-out/Dev-Flow-callflow.html` to compare whether the control-room harness is becoming easier to explain. Graphify output is evidence, not product authority; commit lightweight metrics and notes, not the full generated output by default.


## Product Direction

Dev-Flow is a local-first control room for parallel AI coding workers.

The product is not a coding agent, model provider, memory framework, IDE workflow, or software-factory ritual. Dev-Flow owns the boring but sacred control-plane pieces around replaceable workers:

- task state
- isolated workspaces
- locks and ownership
- worker process lifecycle
- status and logs
- result bundles
- verification evidence
- merge readiness

Workers can be shell commands today and Aider, Hermes, OpenCode, Codex, Claude Code, local models, manual packets, or future tools later. The current code-changing runtime intentionally keeps shell workers as the stable direct editor, with manual proof-agent handoffs and registry-backed local patch workers producing bounded evidence that Dev-Flow reviews, applies, verifies, and promotes separately. Future worker types must be introduced through the registry and adapter-runtime sequence, not wired directly into task execution.

## Non-Negotiable Principles

1. Agents are replaceable. State is sacred.
2. One task gets one isolated workspace and one owner.
3. Visibility is required through plain filesystem artifacts, CLI output, and operating-layer UI projections.
4. Context is durable artifacts, not hidden magic memory.
5. Autonomy is earned by reliable status, logs, recovery, and reviewable results.

## Current Control-Room Contract

The stable core is Dev-Flow-owned task state plus explicit worker execution, evidence, verification, and promotion gates. Shell workers are the current direct code-changing runtime. Local/remote model profiles describe model capability and cost/locality; command surfaces describe authority. Advisory, patch-proposal, local WorkerEvidence, shell execution, verification, apply, and promotion are separate Dev-Flow surfaces. A model profile should not be named or restricted as a single job unless it is intentionally a separate surface wrapper.

The current product should make automation usable without making it mysterious:

- Brainstorm can use an advisory model and must show which model/profile is being used.
- Creating a task should create real task state and surface the task immediately.
- Starting work should name the worker, run in the task workspace, and produce logs/evidence.
- The orchestrator panel should show the current goal/directive, queue, ready/blocked counts, next safe action, and the exact command or UI action that will move work forward.
- Worker lanes should be task-centric: task title, worker/model, status, last activity, changed/evidence files, and available controls.
- Review queue should explain why each item is or is not ready.
- Evidence stream should link concrete events/logs/artifacts to tasks.
- System health counts should be explorable; if it says `7 active`, the operator should be able to see the seven tasks.

Major cleanup should preserve this contract while making the architecture easier to navigate. Use Graphify checkpoints especially around `src/devflow/cli.py`, `src/devflow/control_room/service.py`, `src/devflow/control_room/loop_engine.py`, `src/devflow/control_room/task_next_gate.py`, operating-layer modules, and legacy/shim surfaces.

Detailed command coverage follows as reference. Do not load or validate every command for a focused UI change.

Stable commands:

```bash
devflow --help
devflow init
devflow doctor
devflow git status
devflow git checkpoint --message "chore: checkpoint verified work"
devflow git checkpoint --message "chore: checkpoint verified work" --yes
devflow sync-main
devflow reconcile
devflow freshness loop
devflow freshness loop --json
devflow freshness loop --all-projects
devflow freshness loop --all-projects --json
devflow freshness run --max-iterations 3
devflow freshness run --all-projects --max-iterations 3
devflow freshness run --max-iterations 3 --create-tasks
devflow freshness run --max-iterations 3 --execute-workers --max-parallel 2
devflow freshness run --max-iterations 3 --execute-verification --max-parallel 2
devflow freshness create-batch <goal_id> <batch_id>
devflow freshness worker-batch <goal_id> <batch_id> --max-parallel 2
devflow freshness verify-batch <goal_id> <batch_id> --max-parallel 2
devflow loop init <loop_id> --template goal-autopilot
devflow loop show <loop_id>
devflow loop list
devflow loop run <loop_id> --max-iterations 5 --allow-workers --allow-verify --allow-promote
devflow scheduler status
devflow scheduler status --json
devflow scheduler retry <task_id> --reason "retry after focused repair"
devflow scheduler retry <task_id> --reason "retry after focused repair" --json
devflow question list
devflow question list --json
devflow question show <question_id>
devflow question show <question_id> --json
devflow question answer <question_id> --answer "use the existing API"
devflow question resolve <question_id> --reason "superseded by updated scope"
devflow goal init <goal_id> --from <brief.md>
devflow goal status <goal_id>
devflow goal next <goal_id>
devflow goal activate <goal_id> --reason "ready to execute"
devflow goal pause <goal_id> --reason "waiting on review"
devflow goal block <goal_id> --reason "needs human answer"
devflow goal complete <goal_id> --reason "all task slices promoted and reviewed"
devflow goal archive <goal_id> --reason "superseded"
devflow dashboard
devflow status --json
devflow supervisor policy --json
devflow supervisor packet --json
devflow supervisor route-message "raw Telegram text" --json
devflow hermes imessage-check --json
devflow map init
devflow map show
devflow map check
devflow project create "Factory Scheduler"
devflow project create "Local Experiment" --source-control none
devflow project import /path/to/existing/repo
devflow project list
devflow project show factory-scheduler
devflow project status factory-scheduler
devflow project doctor factory-scheduler
devflow project archive factory-scheduler
devflow project remove factory-scheduler --registry-only
devflow project connect-github factory-scheduler --remote-url <url>
devflow dashboard --all-projects
devflow status --all-projects --json
devflow task --help
devflow task create "example task"
devflow task create --project factory-scheduler "example task"
devflow task run <task_id> --worker shell -- /bin/sh -c "echo hello > result.txt"
devflow task run <task_id> --project factory-scheduler --worker shell -- /bin/sh -c "echo hello > result.txt"
devflow task run <task_id> --shell "echo hello > result.txt"
devflow task run <task_id> --worker qwopus-implementer
devflow task run <task_id> --worker gemma4-12b-qat-implementer
devflow task review-patch <task_id>
devflow task review-patch <task_id> --project factory-scheduler
devflow task review-patch <task_id> --agent qwopus-implementer
devflow task review-patch <task_id> --agent gemma4-12b-qat-implementer
devflow task patch-dry-run <task_id>
devflow task patch-dry-run <task_id> --project factory-scheduler
devflow task patch-dry-run <task_id> --agent qwopus-implementer
devflow task patch-dry-run <task_id> --agent gemma4-12b-qat-implementer
devflow task apply-patch <task_id> --agent qwopus-implementer
devflow task apply-patch <task_id> --agent gemma4-12b-qat-implementer
devflow task apply-patch <task_id> --project factory-scheduler --agent qwopus-implementer
devflow task apply-patch <task_id> --run-id <run_id>
devflow task verify <task_id> --shell "test -f result.txt"
devflow task verify <task_id> --project factory-scheduler --shell "test -f result.txt"
devflow task local <task_id> --agent qwen-planner
devflow task local <task_id> --agent qwopus-implementer
devflow task local <task_id> --agent gemma-reviewer --input-worker qwopus-implementer
devflow task fit <task_id>
devflow task fit <task_id> --json
devflow task scout <task_id> --role all
devflow task scout <task_id> --role risk --json
devflow task route <task_id>
devflow task route <task_id> --json
devflow task scorecard <task_id>
devflow task scorecard <task_id> --json
devflow task list
devflow task list --project factory-scheduler
devflow task list --active
devflow task list --closed
devflow task show <task_id>
devflow task show <task_id> --project factory-scheduler
devflow task review <task_id> --project factory-scheduler
devflow task next-action <task_id> --project factory-scheduler
devflow task review-ready
devflow task review-ready --json
devflow task review-ready <task_id> --json
devflow task review-ready <task_id> --project factory-scheduler --json
devflow task capsule <task_id>
devflow task capsule <task_id> --project factory-scheduler
devflow task packet <task_id>
devflow task packet <task_id> --project factory-scheduler
devflow task log <task_id>
devflow task log <task_id> --project factory-scheduler
devflow task promote-preview <task_id>
devflow task promote-preview <task_id> --project factory-scheduler
devflow task promote <task_id>
devflow task promote <task_id> --project factory-scheduler
devflow push-main
devflow task close <task_id> --outcome rejected --reason "superseded by manual repair"
devflow task cleanup <task_id> --preview
devflow task cleanup <task_id> --apply
devflow task prune-closed --preview --older-than 30d
devflow task prune-closed --apply --older-than 30d
devflow task orchestrate <task_id> --plan-only
devflow worker validate-outcome <path-to-outcome-json>
devflow knowledge capture --from-task <task_id>
devflow knowledge capture --from-validation <path-to-validation-json>
devflow knowledge list
devflow knowledge show <knowledge_id>
devflow knowledge promote <knowledge_id>
devflow knowledge reject <knowledge_id>
devflow knowledge search "<query>"
devflow idea capture "raw idea"
devflow idea list
devflow idea show <idea_id>
devflow idea classify <idea_id> --maturity goal_ready
devflow idea park <idea_id> --reason "safe later"
devflow idea promote <idea_id> --to goal --rationale "human reviewed"
devflow idea create-goal <idea_id> --dry-run
devflow idea create-goal <idea_id>
devflow idea create-task <idea_id> --dry-run
devflow idea create-task <idea_id>
devflow idea archive <idea_id> --reason "superseded"
devflow dogfood list
devflow dogfood show <case_id>
devflow dogfood run --suite production-readiness
devflow dogfood run --suite production-readiness --keep-runs 3
devflow dogfood run --suite production-readiness --write-root-runtime-evidence
devflow dogfood score <run_id>
devflow dogfood report <run_id>
devflow maintenance reset-dogfood-state --preview
devflow maintenance reset-dogfood-state --yes
devflow maintenance reset-test-state --preview
devflow maintenance reset-test-state --yes
devflow maintenance repair-state --preview
devflow maintenance repair-state --yes
devflow release readiness --pytest-evidence <pytest-log> --stale-context-evidence <stale-context-log>
devflow agent show devflow-shell-worker
devflow agent show devflow-manual-codex-worker
devflow agent list --json
devflow agent show devflow-shell-worker --json
devflow agent show local-gemma4-qat --json
devflow agent policy --json
devflow agent catalog --json
devflow agent catalog --provider ollama --json
devflow agent add-provider local_gateway --adapter openai_compatible --base-url http://127.0.0.1:8000/v1 --api-key-env LOCAL_GATEWAY_API_KEY --dry-run --json
devflow agent add-provider local_gateway --adapter openai_compatible --base-url http://127.0.0.1:8000/v1 --api-key-env LOCAL_GATEWAY_API_KEY --json
devflow agent add-model --provider ollama --model <model_id> --authority read-only --role local_senior_worker --dry-run --json
devflow agent add-model --provider ollama --model <model_id> --authority patch-proposer --role implementation_worker --json
devflow agent add-model --provider openrouter --model <remote/model-slug> --authority advisory --role frontier_planner_architect_reviewer --json
devflow agent context-pack <task_id> qwopus-implementer --role implementation_worker --json
devflow agent evidence <task_id> --json
devflow agent discover-local --json
devflow agent select-local <task_id> --role implementation_worker --json
devflow agent audition <task_id> --job review-debug --dry-run --json
devflow agent audition <task_id> --job review-debug --execute --json
devflow agent run --task <task_id> --profile local-gemma4-qat --dry-run --json
devflow agent run --task <task_id> --profile local-gemma4-qat --json
devflow agent advise --profile hermes-qwen37plus --job gap-analysis --dry-run --json
devflow agent advise --profile hermes-qwen37plus --job gap-analysis --json
devflow agent advise --profile hermes-sonnet46 --task <task_id> --job review --json
devflow agent propose-patch --task <task_id> --profile <patch-surface-profile> --json
devflow agent packet <task_id> devflow-shell-worker
devflow agent packet <task_id> devflow-manual-codex-worker
devflow task run <task_id> --worker devflow-shell-worker -- <command>
devflow task run <task_id> --worker devflow-manual-codex-worker
```

The preferred shell-worker form is `devflow task run <task_id> --worker shell -- <command>`. The `--shell "<command>"` form remains supported.

The registry-visible shell alias is `devflow-shell-worker`. It uses the same stable shell adapter and isolated workspace boundary as the daily shell command, but writes agent-scoped packet/log/result evidence under `.devflow/tasks/<task_id>/agents/devflow-shell-worker/` so registry, packet, and dogfood surfaces can inspect the shell lane. `agent list --json`, `agent show --json`, and `agent packet` include `runtime_contract` with execution surface, `task_run_allowed`, `agent_run_allowed`, `packet_allowed`, refusal reason, next command, and evidence contract. Provider-backed and frontier read-only agents still refuse `task run`; frontier read-only agents may produce local packets only when their runtime contract reports `packet_allowed: true`.

The project-management form is `devflow project create "Name"`. It creates a separate local project root under the configured projects root, initializes local Git by default, creates that project's own `.devflow/` scaffold, and registers the project in `~/.devflow/registry/projects.json`. It does not create a GitHub repository, add a remote, push, publish, or create a hidden initial commit by default. For local-Git managed projects, create an explicit local baseline from the project root with `devflow git checkpoint --message "chore: initialize project baseline" --yes` before creating project-scoped tasks; `task create --project` refuses unborn managed Git projects so copied workspaces and promotion previews have a real baseline commit. Existing project roots can be registered with `devflow project import /path/to/project`. `devflow dashboard --all-projects` renders the registry as a multi-project control-room view while preserving the existing single-project dashboard behavior.

A missing registered project path is handled as explicit human-decision registry hygiene. The first command is `devflow project doctor <project_id>`. If the project exists elsewhere, the human repairs the registry by importing or re-registering the real project root. If the project was temporary, deleted, or intentionally retired, the default cleanup is `devflow project archive <project_id>` so the record remains audit-visible through `project list --include-archived` but drops out of normal lists and all-project scans. `devflow project remove <project_id> --registry-only` is reserved for junk registry entries that should not remain in audit history. Read-only all-project surfaces report missing paths and recommend `project doctor`; they do not recreate, archive, remove, publish, push, or call providers.

Project task state is project-local. Without `--project`, task commands resolve the nearest ancestor that owns a `.devflow/` directory, falling back to the current directory only when no project-local state exists. With `--project <project_id>`, task create/list/show/run/verify/packet/review/next-action/log/review-patch/patch-dry-run/apply-patch/promote-preview/promote resolve the project root from `~/.devflow/registry/projects.json` and read or write that project's `.devflow/tasks/` and `.devflow/workspaces/` as appropriate. Task IDs remain unique within each project, not globally; cross-project output displays task refs as `<project_id>:<task_id>`. Project-scoped `promote-preview` is read-only. Project-scoped `promote` preserves the existing human confirmation and promotion safety gates while applying changes to the registered project root, not the caller's current directory.

When `--project` is omitted, task commands walk upward from the current directory to the nearest ancestor containing `.devflow/`. This keeps project-local state authoritative when commands are run from nested subdirectories and avoids accidental nested `.devflow/` split-brain state. If no ancestor contains `.devflow/`, bootstrap-compatible commands use the current directory.

The proof-agent form is `devflow task run <task_id> --worker devflow-manual-codex-worker`. It creates a Codex-ready manual handoff and bounded packet for a human-launched worker. The worker may edit only `.devflow/workspaces/<task_id>/` and may write evidence only under `.devflow/tasks/<task_id>/agents/devflow-manual-codex-worker/`. Dev-Flow remains responsible for verification, merge readiness, and human-controlled promotion.

The Project Code Map form is `CODE_MAP.md` plus `devflow map init`, `devflow map show`, and `devflow map check`. The map is a human-authored orientation artifact. When present, `devflow task packet <task_id>` includes a bounded excerpt so workers can orient before broad repo scans. The map is read-only context, not canonical task state, and it does not route models, call providers, or generate itself from source.

The registry-backed local patch form is `devflow task run <task_id> --worker qwopus-implementer` or `devflow task run <task_id> --worker gemma4-12b-qat-implementer` when that model is installed and selected by explicit local-agent evidence. It calls local Ollama, writes `proposal.patch`, `raw_output.md`, `result.md`, `run.json`, and `logs/worker.log` under `.devflow/tasks/<task_id>/agents/<worker_id>/`, and stops. Dev-Flow remains responsible for explicit patch review, dry-run preview, application to the isolated workspace, verification, merge readiness, and human-controlled promotion. The `review-patch --agent` and `patch-dry-run --agent` forms normalize agent patch evidence into `.devflow/tasks/<task_id>/local-model-runs/<run_id>/`; apply-patch refuses mutation unless matching fresh acceptable review and dry-run evidence exists in the resolved project root. Normalized local-model patch review and patch dry-run evidence are documented in [docs/architecture/patch-evidence-ladder.md](architecture/patch-evidence-ladder.md); dry-run preview is evidence only and does not mutate source or workspace files.

The model onboarding form is `devflow agent catalog --json`, `devflow agent add-provider ...`, and `devflow agent add-model ...`. Catalog is read-only: it shows configured providers, registered profiles, runtime contracts, missing provider env vars, installed local Ollama models, and unregistered installed Ollama models. `add-provider` writes one `.devflow/providers/<provider_id>.yaml` after validation. `add-model` writes or upserts one `.devflow/agents/registry.yaml` profile from safe templates, deriving a deterministic profile id unless `--profile-id` is supplied. Local Ollama `read-only` profiles map to `agent run`, local Ollama `patch-proposer` profiles map to the existing local `proposal.patch` runtime, and remote `advisory` / `patch-proposer` profiles map to `agent advise` / `agent propose-patch`. Remote slugs for OpenRouter, OpenAI-compatible, OpenAI chat, Anthropic, Gemini, and custom configured providers are accepted without remote catalog calls. All generated profiles remain evidence-only or proposal-only: no autonomous routing, direct main checkout edits, worker-owned verification, promotion, commit, merge, or push.

The local agent discovery form is `devflow agent discover-local --json` and `devflow agent select-local <task_id> --role implementation_worker --json`. Discovery calls only local Ollama, parses installed model manifests, and derives conservative capability profiles. Selection ranks installed registry agents for the requested role and writes `.devflow/tasks/<task_id>/agent-selection.json`. This is the current model-agnostic selection boundary: Dev-Flow should choose the best eligible installed profile for the explicit role from registry and manifest evidence, not from hard-coded model names. It does not run a worker, silently substitute a model, apply patches, verify, promote, merge, push, or call remote providers. Unregistered installed Ollama models are surfaced by catalog and become selectable only after explicit `agent add-model`. `task run` remains explicit and uses the selected worker only when the human or dogfood ladder invokes it.

The task-fit/context-routing evidence form writes derived artifacts only. It classifies task fit, context size, scout signals, candidate eligibility, rejected candidates, unresolved roles, and post-run quality signals. It does not run workers, call remote providers, silently substitute models, verify, promote, commit, push, or create pull requests.

The remote advisory form is `devflow agent advise --profile <profile_id> [--task <task_id>] --job <gap-analysis|review|status> --json`. Advisory runs are remote model evidence, not worker execution. They build bounded repo or task context, call only the configured provider for that profile when not in `--dry-run`, and write prompt, response, raw response, and `run.json` evidence under `.devflow/reports/agent-advisory-runs/<run_id>/` for repo-scope runs or `.devflow/tasks/<task_id>/agent-advisory-runs/<run_id>/` for task-scope runs. Run metadata records provider, model, prompt/response paths, usage when returned, recommendations, and `will_create_tasks`, `will_run_workers`, `will_apply_patch`, `will_verify`, `will_promote`, `will_commit`, `will_push`, and `will_write_source` as false. Provider config stores only environment variable names, never literal keys.

The remote patch-proposal form is `devflow agent propose-patch --task <task_id> --profile <patch-surface-profile> --json`. It is an explicit human-invoked execution surface, not a Hermes cron command and not a task-run worker. Real model profiles should remain model/capability identities; a patch surface profile is a separate wrapper only when Dev-Flow needs that narrower write contract. It writes only `proposal.patch`, raw output, `run.json`, and summary evidence under `.devflow/tasks/<task_id>/agents/<profile_id>/`. The default `DEVFLOW_OPENROUTER_PATCH_PROMPT_MODE=standard` path uses bounded TaskPacket/context-pack evidence; `DEVFLOW_OPENROUTER_PATCH_PROMPT_MODE=minimal` is an opt-in path for tiny explicit repair proposals that sends only task identity, referenced target snippets, verification guidance, and the JSON patch schema. The proposal must still pass the existing `task review-patch`, `task patch-dry-run`, `task apply-patch`, verification, and promotion gates before source changes can land.

OpenRouter operator note: Hermes may be working with OpenRouter while a Codex/Desktop shell still reports `OPENROUTER_API_KEY` as unset, because Hermes keeps its local env in `~/.hermes/.env` and that file is not automatically inherited by Codex subprocesses, `launchctl`, or normal shell startup files. For one-off direct CLI proofs, load only the `OPENROUTER_API_KEY` value from `~/.hermes/.env`; do not source the whole Hermes env file because unrelated values may contain spaces or shell-sensitive paths. Minimal Flash patch proposals must disable provider-side reasoning with `{"enabled": false, "exclude": true}`. Do not use `reasoning.effort=minimal` for the minimal patch path: it can spend the entire 2,048-token completion budget on hidden reasoning, return `finish_reason: length`, `content: null`, and write failed evidence even though OpenRouter itself is working.

The role-scoped context-pack form is `devflow agent context-pack <task_id> <agent_id> --role <role> --json`. It writes derived context-pack evidence under `.devflow/tasks/<task_id>/context-packs/` from canonical TaskPacket data, without becoming canonical task state or routing authority. The derived agent-evidence form is `devflow agent evidence <task_id> --json`; it summarizes shell, manual proof-agent, local patch, and local model WorkerEvidence paths for inspection and operating-layer projection without mutating task state.

The orchestration policy form is `devflow task orchestrate <task_id> --plan-only`. It writes task-local policy evidence with Git/DevMode baseline, allowed roles, context layers, write boundaries, stop conditions, and human promotion requirements. It does not execute workers, call provider APIs, route autonomously, apply patches, verify, promote, or mutate main.

The guardrail outcome metadata form is `devflow worker validate-outcome <path-to-outcome-json>`. It validates worker outcome metadata and writes validation evidence only. It does not run agents, apply patches, verify code, promote, route models, or mutate `task.yaml`.

The freshness loop form is `devflow freshness loop`. It runs one control-loop iteration against canonical goal and task state, writes a derived snapshot to `.devflow/freshness/latest.json`, appends `.devflow/freshness/events.jsonl`, updates each goal's derived `.devflow/goals/<goal_id>/loop-state.json`, records the loop-start Git checkpoint/push decision, projects per-goal loop state plus parallel-safe task lane recommendations, groups ready lanes into conflict-aware parallel batches using declared `shared_files`, projects conflict-aware shell-worker batches from concrete slice `worker_policy` command lists, projects conflict-aware verification batches from concrete slice `verification_policy` command lists, and reports stale or contradictory goal/task/handoff guidance. `devflow freshness run --max-iterations N` repeats that PLC-style loop within a strict iteration bound, persists a derived run report under `.devflow/freshness/control-runs/`, stops when state is stable, and stops before dispatch when Git checkpoint/push/sync/repair or human decisions are required. `devflow freshness run --all-projects --max-iterations N` repeats bounded-parallel, read-mostly scans across registered project roots, writes an aggregate bounded run report under `~/.devflow/freshness/control-runs/`, and refuses dispatch flags because project-level integration remains a controlled lane. `devflow freshness create-batch <goal_id> <batch_id>` creates tasks for one currently projected conflict-safe parallel batch, using the existing goal slice task-creation path and serializing canonical state writes. `devflow freshness run --create-tasks` is the explicit task-creation dispatch mode: it may create the first currently projected parallel task batch in a safe iteration, then loops again so the resulting checkpoint opportunity is surfaced before more work. `devflow freshness worker-batch <goal_id> <batch_id> --max-parallel N` executes one currently projected safe shell-worker batch with task-grained parallel subprocesses while preserving existing `run_shell_task` locks, logs, task events, and workspaces. `devflow freshness run --execute-workers` is the explicit worker dispatch mode: it may run the first currently projected shell-worker batch in a safe iteration, then loops again so changed workspace/task evidence is observed and the next Git checkpoint opportunity is surfaced before more work. `devflow freshness run --execute-verification` is the explicit verification dispatch mode: it may run the first currently projected verification batch in a safe iteration, then loops again so the next Git checkpoint opportunity is surfaced before more work. `devflow freshness verify-batch <goal_id> <batch_id> --max-parallel N` executes one currently projected safe verification batch with task-grained parallel subprocesses while preserving the existing `verify_task` locks, logs, `verification.json`, and task events. Batch creation, worker runs, and verification write derived reports under `.devflow/freshness/task-batch-runs/`, `.devflow/freshness/worker-runs/`, `.devflow/freshness/verification-runs/`, and `.devflow/freshness/control-runs/`; those reports are evidence about bounded control activity, never goal-completion certificates. The single-iteration CLI loop still projects only. `devflow freshness loop --all-projects` runs that same project-local loop across registered project roots with bounded concurrency, writes each project's local freshness snapshot, reassembles aggregate output in registry order, and writes a registry-level snapshot to `~/.devflow/freshness/latest-all-projects.json`. Missing active project paths are reported as human-decision items pointing to `devflow project doctor <project_id>` instead of crashing the loop. When repair is ambiguous, the loop exits with a human-decision status instead of rewriting docs, canonical goal artifacts, registry entries, commits, remotes, spawning workers, or starting verification processes.

The reusable automation-loop form is `devflow loop`. `devflow loop init <loop_id> --template goal-autopilot` writes `.devflow/loops/<loop_id>/loop.yaml`; `loop show` and `loop list` expose those durable definitions. `devflow loop run <loop_id>` reads active goal/freshness projections and may create ready parallel-safe tasks by default. Shell-worker batches require `--allow-workers`; verification batches require `--allow-verify`; promotion requires the loop config's `policy.allow_promotion: true` plus `--allow-promote`, passed task verification, a clean promotion preview, and no open questions/blockers. Goal-linked tasks also honor `goal-link.yaml` promotion policy and high-risk lanes stop unless the loop policy explicitly allows them. Standalone verified tasks may be promoted when the loop-level gates pass. Every run writes `.devflow/loops/<loop_id>/runs/<run_id>.json` with final status, iteration count, created tasks, worker runs, verification results, promotion previews, promotions completed, stop reason, and next safe action. V1 refuses unknown actions and does not enable provider-backed workers, remote APIs, push, PR creation, publication, auto-commit, background daemons, or arbitrary command loops outside DevFlow task/workspace state.

Knowledge Foundry commands write proposed/promoted/rejected reusable notes under `.devflow/knowledge/`. Knowledge promotion is separate from task promotion; capture never silently converts ideas into tasks or goals. This is local human-reviewed curation, not ML training, hidden agent memory, vector search, or RAG.

The Idea Foundry form is `devflow idea capture/list/show/classify/park/promote/create-goal/create-task/archive`. It stores project-local intake evidence under `.devflow/ideas/<idea_id>/`, keeps raw ideas separate from goals and tasks until explicit bridge creation, and records human classification, parking, promotion, and archival decisions. Parking is non-destructive: `devflow idea park` preserves `raw.md` and the idea event history while marking the idea safe-later with a reason. `devflow idea create-goal` and `devflow idea create-task` require prior matching human promotion evidence, write bidirectional idea-to-goal/task links, and create Dev-Flow state only. Idea Greenhouse V1 is the current operating-layer projection of these local records. It does not run models, cluster ideas, or auto-create tasks/goals; promotion remains an explicit human decision. Idea creation commands do not run workers, call providers, verify, promote code, commit, push, open pull requests, or route models.

The dogfood production-readiness form is `devflow dogfood run --suite production-readiness`. It runs deterministic local cases against existing Dev-Flow control-room surfaces and writes the final scorecard/report under `.devflow/dogfood/`. Dogfood reports are disposable runtime evidence: by default each run keeps only the latest `.devflow/dogfood/runs/<run_id>` and prunes older run directories so old test evidence does not accumulate in the active checkout. Use `--keep-runs <n>` only when release/debug work intentionally needs more local run history. Task-producing cases execute in a temporary scratch project by default so dogfood does not create root `.devflow/tasks/task-*`, workspaces, or worktrees in the active project. `--write-root-runtime-evidence` is an explicit unsafe/noisy opt-in for root-state dogfood evidence. The suite measures safety, pipeline correctness, context efficiency, worker artifact quality, recovery handling, knowledge capture, registry/runtime contract visibility, operating-layer visual QA, and lightweight behavior. The visual QA case requires desktop/mobile current and baseline artifacts for `devflow operating-layer visual-qa`, accepts deterministic fallback PNG/SVG evidence as the minimum, upgrades to external/Appshot PNGs when present, and uses optional Playwright browser rasters when available. Dogfood closes task records it creates in the scratch project, or in the root only when root evidence is explicitly requested, with the `evidence-only` outcome after each case. It is not autonomous model execution: it does not call providers, route workers, promote, push, create a database, create a dashboard, run a daemon, use vector search/RAG/embeddings, or train models.

The release-readiness form is `devflow release readiness --pytest-evidence <pytest-log> --stale-context-evidence <stale-context-log>`. It is a read-only milestone gate over explicit evidence: clean Dev-Flow Git status, captured full-suite pytest output, latest production-readiness dogfood Silver-or-better scorecard, operating-layer visual QA desktop/mobile evidence, stale-context scan evidence, and a standard handoff report with one next safe action. It does not run heavy suites, mutate task state, promote, push, tag, build, or publish; it makes the release gate explicit after the expensive verification commands have already been run and captured.

The local operating-layer form is `devflow operating-layer snapshot --json`, `devflow operating-layer serve --host 127.0.0.1 --port 8765`, and `devflow operating-layer install-service` for a per-user macOS LaunchAgent that starts the local server at login. It is the approved UI contract for a browser-friendly control-room surface. It composes existing project, goal, task, idea, freshness, verification, evidence, question, lane, and promotion projections into one derived snapshot and serves the bundled Python-owned UI over that same snapshot. The canonical first viewport is the actual control loop: Brainstorm, Pipeline, Worker lanes, Review queue, and Evidence stream. Idea Greenhouse V1 is visible in this surface as the current local intake UI for Raw / Clarify / Candidate / Promoted / Parked / Archived idea lanes derived from `.devflow/ideas/`. The `public/` static marketing/simulator page is not the active Dev-Flow UI and must not be used for product validation. The normal browser loop starts with a DeepSeek V4 Flash Free brainstorm chat that writes local transcript/spec/plan evidence, then escalates through exact approval-gated task creation, shell worker execution, verification, and human promotion. The brainstorm model is advisory evidence only; it does not edit files, run workers, verify, promote, commit, push, or route work autonomously. Advanced Commands may execute supervisor-classified read-only Dev-Flow commands through the local server. The approval-gated browser mutation path is limited to exact idea capture, idea parking, idea archive, task creation, shell worker execution, task verification, and task promotion commands after explicit human approval; the server rechecks the supervisor classifier, refuses placeholder idea/title/command text, limits browser worker runs to `--worker shell`, blocks local/provider model commands, and preserves the existing verification and promotion safety gates. Non-shell worker execution, patch application, cleanup apply, sync, push, project publication, provider-backed task execution, autonomous routing, and other broad mutations remain blocked for trusted CLI execution. The filesystem remains the source of truth; the snapshot is derived and disposable. See [docs/architecture/local-operating-layer-ui.md](architecture/local-operating-layer-ui.md).

The legacy local Ollama advisory form is `devflow task local <task_id> --agent qwen-planner`, `devflow task local <task_id> --agent qwopus-implementer`, or `devflow task local <task_id> --agent gemma-reviewer --input-worker qwopus-implementer`. It runs `ollama run <model>` through a local subprocess, writes prompt/response/run metadata under `.devflow/workspaces/<task_id>/local-workers/<worker-name>/`, and updates `task.yaml` plus hash-chained events. It does not write `proposal.patch`, auto-edit repo files, parse model output as truth, route autonomously, verify, commit, merge, promote, or call remote provider APIs.

The registry-backed local model worker-pool form is `devflow agent run --task <task_id> --profile local-gemma4-qat --dry-run --json` for preview and `devflow agent run --task <task_id> --profile local-gemma4-qat --json` for a long-context/vision local WorkerEvidence run. Use `local-qwen25-coder-14b` when code-specialist local review is the better fit. Profiles include machine class, weight class, model role name, capability metadata, caution notes, and manifest verification command. The real slice builds a bounded TaskPacket, calls `local_model_client.py`, writes WorkerEvidence under `.devflow/tasks/<task_id>/local-model-runs/<run-id>/`, caps raw output, captures failure, and stops. `local-gemma4-qat` uses a compact evidence packet plus native Ollama `/api/chat` with thinking disabled when required by the model/template. It does not edit source files, write `proposal.patch`, apply patches, verify, commit, merge, push, promote, or mutate canonical task state. See [docs/architecture/local-model-worker-pool.md](architecture/local-model-worker-pool.md).

Do not implement these in the first milestone:

- Aider
- Hermes worker/runtime adapter (external operator gateway docs are allowed)
- OpenCode
- memory
- complex scheduling
- autonomous routing
- remote provider-backed task-run adapter calls before explicit promotion into the runtime contract
- autonomous remote provider escalation beyond explicit `agent advise` / `agent propose-patch` evidence commands
- old task-packet workflow orchestration
- PR automation
- autonomous browser/web dashboard mutation surfaces
- token-context routing helpers beyond the current read-only planning helper
- autonomous task-fit/context routing runtime beyond the Milestone 17 evidence commands
- hidden or autonomous commit, push, merge, or pull request creation

## Runtime Structure

```text
.devflow/
  tasks/<task_id>/
    .lock/                  # live only during task-local mutations
    task.yaml
    events.jsonl
    verification.json
    closure.json
    cleanup.json
    logs/
      worker.log
      verify.log
    agents/devflow-manual-codex-worker/
      handoff.md
      packet.json
      result.md
      questions.jsonl
      worker_failed.json
    local-model-runs/<run-id>/
      run.json
      packet.md
      response.md
      raw_output.txt
      error.txt
    agent-advisory-runs/<run-id>/
      prompt.md
      response.md
      response.raw.json
      run.json
    agents/<patch-surface-profile>/
      proposal.patch
      raw_output.md
      result.md
      run.json
  reports/agent-advisory-runs/<run-id>/
    prompt.md
    response.md
    response.raw.json
    run.json
  prune-runs/<run-id>.json
  workspaces/<task_id>/
    local-workers/<worker-name>/
      prompt.md
      response.raw.md
      response.md
      run.json
      stderr.log
```

The filesystem is the source of truth. `task.yaml` is canonical current state. `events.jsonl` is append-only evidence. New task event records include a monotonic `event_index`, `previous_event_hash`, and `event_hash` so `doctor` can detect malformed or edited task event streams. `verification.json` stores the latest verification result. Worker and verification logs are raw evidence. Worker and verification commands run only inside `.devflow/workspaces/<task_id>/`.

Current task-state artifacts use schema version 1. New `task.yaml`, `verification.json`, `merge-readiness.json`, and `summary.json` files record that version; missing task schema versions are treated as version 1 for backward compatibility, while unknown task schema versions are refused.

Closed-task cleanup and pruning are separate retention controls. `devflow task cleanup <task_id> --preview` and `--apply` remove only closed-task runtime artifacts under `.devflow/workspaces/<task_id>` or `.devflow/worktrees/<task_id>/<worker>`, while retaining `.devflow/tasks/<task_id>/` evidence. `devflow task prune-closed --preview --older-than <duration>` reports old closed-task evidence directories eligible for deletion without writing audit files; `--apply` deletes only safe, eligible `.devflow/tasks/<task_id>/` evidence after repeating the same checks and writes `.devflow/prune-runs/<run-id>.json` as audit evidence. It refuses active tasks, missing closure metadata, symlinked/path-traversal evidence paths, and anything outside `.devflow/tasks/`.

The maintenance surface is explicit and conservative. `devflow maintenance reset-dogfood-state --preview` lists only disposable local-test evidence: unpromoted task records whose title identifies dogfood or smoke-test work, closed `evidence-only` task records whose close reason identifies dogfood, their matching workspace/worktree runtime directories, and `.devflow/dogfood/` run reports. `--yes` removes only those paths, preserves tracked seed/config/context files and real or promoted task evidence, and refuses symlink/path escapes outside `.devflow`. `devflow maintenance reset-test-state --preview` is the explicit post-test full reset for local app/dogfood test runs: it lists all `.devflow/tasks/task-*`, `.devflow/workspaces/task-*`, `.devflow/worktrees/task-*`, and `.devflow/dogfood/` artifacts while preserving project-level state such as config, goals, knowledge, release logs, and tracked seed files. `--yes` applies the same allowlist and symlink/path-escape checks. `devflow maintenance repair-state --preview` reports missing task baseline artifacts, and `--yes` restores missing `events.jsonl`, `questions.jsonl`, `result.md`, `verification.json`, `logs/worker.log`, `logs/verify.log`, and `merge-readiness.json` without overwriting existing evidence. `doctor` reports missing baseline artifacts read-only.

Review Capsules are read-only rendered views over that evidence. After worker output, verification, finalization, or promotion preview, Dev-Flow prints a compact capsule with task identity, status, worker/workspace, Git branch and latest commit when available, verification result, promotion readiness, changed files, and inline contents for small changed text files. The flow is:

1. Worker completes task.
2. Dev-Flow records canonical evidence.
3. Dev-Flow renders a Review Capsule directly in command output.
4. The human makes an explicit decision.
5. The human promotes, rejects/closes, or requests changes.

Capsules do not create review files by default, duplicate canonical evidence, mutate task status, promote, close, or weaken safety gates. `devflow task capsule <task_id>` re-renders the current view manually; `--project <project_id>` resolves the registered project root before rendering; `--export-md` writes one explicit markdown export under the task evidence folder only when requested.

`devflow task review-ready [<task_id>] --json` is a read-only scorecard over existing task evidence. It classifies active tasks as `ready_for_review`, `needs_verification`, `verification_failed`, `needs_promotion_preview`, `blocked`, `worker_failed`, `running`, or `not_ready`; includes concrete blockers, evidence paths, a deterministic sorting score, and the safest next command; and refuses to mark a task ready when canonical verification or promotion-readiness evidence is malformed, stale, or missing. It does not run workers, verify, create promotion previews, render or export capsules, promote, close, mutate task state, route models, or call providers. `--project <project_id>` resolves the registered project root before reading task evidence.

Task-local mutation commands (`run`, `local`, `verify`, `apply-patch`, and `promote`) create `.devflow/tasks/<task_id>/.lock/owner.json` while they own the task. Active locks refuse competing mutations with owner details. Stale locks are removed after the configured stale window.

Manual proof-agent files are evidence artifacts, not canonical state. `task show` and `dashboard` surface complete, blocked, and failed manual-agent evidence while leaving canonical task state under Dev-Flow control.

The default control-room task path does not create a SQLite database or `.devflow/worktrees/` directory. Shell-worker results stay in the task workspace until a human explicitly previews and promotes verified changes. `devflow task create --git-worktree` is the opt-in Git-native path and creates `.devflow/worktrees/<task_id>/shell/` plus branch/evidence artifacts.

The production direction after the copy-workspace MVP is Git-native worker isolation and promotion: workers run in `.devflow/worktrees/<task_id>/<worker_id>/` on branches like `devflow/<task_id>/<worker_id>`, verification records the exact worker branch commit it checked, and promotion preview reports Git merge readiness instead of only copy-workspace changes. The first opt-in shell-worker slice is active.

## Files To Keep Or Salvage Later

These are useful ingredients, but they must be adapted to the new product shape instead of treated as process authority:

- `src/devflow/cli.py`: current CLI entry point; likely replace argparse with Typer or simplify heavily.
- `src/devflow/runner.py`: salvage small shell execution and verification helpers only; bypass unified-diff runner behavior for the MVP.
- `src/devflow/failures.py`: possible source for simple failure labels later.
- `tests/`: salvage patterns, but expect the first MVP tests to be new shell-worker/control-room tests.
- `pyproject.toml`: keep packaging entry point, but update dependencies when implementation begins.

## Files And Surfaces To Bypass

These belong to the old product direction and should not guide implementation:

- legacy workflow, instruction, and skill copies if encountered outside the active repository tree
- `src/devflow/agents/**`
- `src/devflow/memory.py`
- `src/devflow/worktrees.py`
- `src/devflow/worktree_commands.py`
- `src/devflow/context.py`
- `src/devflow/dag.py`
- `src/devflow/evals.py`
- `src/devflow/traces.py`
- old task-file unified-diff runner
- old task claim/release/transition/status protocol

Bypass does not necessarily mean delete immediately. It means do not treat these files as source of truth for the rebuild.

## Files To Create For The MVP

Expected implementation files:

- `src/devflow/core/paths.py`
- `src/devflow/models/task.py`
- `src/devflow/models/worker.py`
- `src/devflow/services/task_service.py`
- `src/devflow/services/doctor_service.py`
- `src/devflow/services/workspace_service.py`
- `src/devflow/services/worker_service.py`
- `src/devflow/adapters/base.py`
- `src/devflow/adapters/shell.py`
- `tests/test_control_room_shell.py`

Existing files may be simplified instead of duplicated when that keeps the diff smaller.

## Smallest First Implementation Patch

The first code patch should prove a single vertical slice:

1. `devflow --help` and `devflow task --help` expose the CLI entry points.
2. `devflow task create "example task"` creates the stable task artifacts and isolated workspace directory.
3. `devflow task run <task_id> --shell "echo hello > result.txt"` runs in the task workspace, captures `logs/worker.log`, and marks the task complete.
4. `devflow task verify <task_id> --shell "test -f result.txt"` runs in the same task workspace, captures `logs/verify.log`, writes `verification.json`, and marks the task verified.
5. `devflow task list`, `devflow task show <task_id>`, and `devflow dashboard` expose the current state from task files.
6. `devflow task promote-preview <task_id>` shows the isolated workspace changes that would be promoted.
7. `devflow task promote <task_id>` copies verified, human-approved changes back to the main checkout without staging, committing, pushing, or opening a pull request.

Only after that slice stays stable should new runtime behavior be promoted into the contract.

For default copy-workspace tasks, the explicit `devflow task promote <task_id>` command after a reviewed preview is the human approval act. Deletion-applying promotions and Git-native promotions keep the additional confirmation prompt because they can remove files or merge refs.

## Acceptance Gauntlet

Create one shell task, run `echo hello > result.txt`, verify `test -f result.txt`, list it, show it, inspect the dashboard, preview promotion, and promote only after explicit human approval. Before promotion, the command result must exist only under `.devflow/workspaces/<task_id>/`. No worker may mutate the main checkout directly. No provider-backed task-run adapter, database, autonomous browser dashboard mutation surface, or worktree orchestration is part of this acceptance test. The manual proof-agent acceptance path additionally requires `agent show`, `agent packet`, and `task run --worker devflow-manual-codex-worker` to produce bounded handoff/evidence surfaces without executing provider APIs.

## Current Implementation Status

Implemented:

- shell-worker control-room CLI
- init and doctor commands for the local control-room seed structure
- filesystem task state with canonical `task.yaml`
- atomic write-then-replace for canonical `task.yaml`, derived `summary.json`, latest `verification.json`, and `merge-readiness.json`
- per-task artifact directories
- append-only task and system `events.jsonl`
- success, failure, and timeout statuses
- log/result/report artifact writing
- verification command execution inside the task workspace
- POSIX process-group cleanup for shell and verification timeout paths
- verification log writing
- `verification.json` latest-result evidence
- copied scratchpad workspaces under `.devflow/workspaces/<task_id>/`
- tampered workspace refusal before shell or verification commands execute
- symlink skipping during scratchpad copy
- text-only terminal dashboard
- local operating-layer snapshot and supervisor-safe guided browser controls for create/run/verify/promote UI state
- read-only crash/interruption reconciliation reporting for partial event writes, task/system event divergence, interrupted promotion evidence, and inconsistent task artifacts
- stable `devflow-manual-codex-worker` registry contract
- proof-agent bounded packets with role, allowed reads, allowed writes, forbidden writes, required outputs, completion rules, and manual instructions
- manual proof-agent handoff generation without provider API calls, model selection, routing, scheduling, auto-verification, or direct promotion
- durable `devflow loop` definitions and run evidence under `.devflow/loops/`
- goal-autopilot loop runs that can create ready tasks, run shell workers, run verification, preview promotion, and promote verified safe local work only through explicit config and run flags
- task show/dashboard visibility for manual proof-agent complete, blocked-question, and failure evidence
- adapter maturity boundary with only `shell` and `manual` classified as executable `stable_runtime` adapters
- clear task-run refusal for `experimental_readonly` and `planned_not_executable` adapters
- promotion preview from isolated workspace changes
- human-controlled promotion of verified changes to the main checkout
- task closure evidence with explicit outcomes, inactive closed status, and preserved logs/artifacts
- preview-first cleanup for closed tasks that removes only conservative task-owned `.devflow` runtime artifacts on `--apply`
- preview-first pruning for old closed-task evidence that deletes only safe `.devflow/tasks/<task_id>/` evidence on explicit `--apply` and records `.devflow/prune-runs/<run-id>.json`
- `devflow task local` for local Qwen/Qwopus/Gemma advisory evidence capture with 600-second defaults, raw response preservation, stderr capture, and run metadata under the task workspace
- `devflow task run --worker qwopus-implementer` and `devflow task run --worker gemma4-12b-qat-implementer` for canonical local Ollama `proposal.patch` evidence that Dev-Flow applies and verifies separately
- `devflow agent context-pack` and `devflow agent evidence` for derived, non-canonical role context and task-local worker evidence summaries
- `devflow agent discover-local` and `devflow agent select-local` for model-agnostic installed local agent ranking by explicit role
- `devflow agent catalog`, `devflow agent add-provider`, and `devflow agent add-model` for one-command provider/profile onboarding from safe templates
- OpenRouter provider seed config using `https://openrouter.ai/api/v1`, `openai_compatible`, and `OPENROUTER_API_KEY`
- registry-visible simplified Hermes/OpenRouter/local profiles with capability metadata and explicit configured-provider evidence surfaces
- `devflow agent advise` for dry-run or explicit configured-provider advisory evidence without task creation, worker runs, patch application, verification, promotion, commit, or push
- `devflow agent propose-patch` for explicit registry-backed configured-provider patch proposal evidence that still depends on existing patch review/dry-run/apply/verification/promotion gates
- `devflow task orchestrate --plan-only` for plan-only parallel-worker policy evidence
- `devflow worker validate-outcome` for structured guardrail outcome metadata validation
- Knowledge Foundry commands for proposed/promoted/rejected local reusable knowledge notes
- Idea Foundry commands and Idea Greenhouse V1 operating-layer projection for raw idea intake, human classification, non-destructive parking, decision-only promotion, explicit goal/task creation after prior promotion evidence, and archival evidence
- canonical goal lifecycle state under `.devflow/goals/<goal_id>/goal-state.yaml`, with explicit `goal activate/pause/block/complete/archive` commands, lifecycle-aware goal status/next output, freshness dispatch gating for paused/blocked/complete/archived goals, operating-layer lifecycle display, and human-controlled closure recommendations after promoted task-slice evidence

Outside the current product contract:

- autonomous browser/web dashboard mutation surface
- token-context helper (Completed helper; acts purely as a visible planning helper that recommends context strategy. It does not execute token tools, route models, install hooks, or change shell-worker, merge, or verification behavior.)
- autonomous task-fit/context routing runtime beyond the Milestone 17 evidence-only commands. The current local selector ranks eligible installed agents for an explicit role, and the routing evidence commands write derived fit, scout, route, and scorecard artifacts only; they do not autonomously pick the best model for arbitrary tasks, invoke workers, or change shell-worker behavior.
- provider-backed non-shell task-run adapters
- Ollama keep-alive/model-stop controls for local resource pressure
- remote provider-backed registry and adapter-runtime task execution beyond the current shell/manual/local-patch/local-evidence/OpenRouter-evidence guardrails
- SQLite or other databases
- provider-backed `.devflow/worktrees/` orchestration beyond the opt-in shell-worker slice
- multi-worker worktree scheduling, branch-sharing cleanup beyond strict doctor detection, and provider-backed Git worktree promotion beyond the current opt-in shell-worker slice
- vector databases, RAG, ML training, hidden memory, and automatic self-training

> [!IMPORTANT]
> **Current Status**: The operational baseline is proven, and the active product focus is operating-layer usability: make task creation, task visibility, worker/model identity, evidence, verification, close/cleanup, retry, and promotion controls obvious from the browser UI.
> Prior hardening work still matters as guardrails: task/data-sprawl repair, complete task baseline artifacts, scratch-root dogfood defaults, clean prune previews, copy-workspace promotion repair, registry-backed model/profile evidence, and loop-gated local automation. Future autonomy/provider work remains roadmap material until explicitly promoted into runtime behavior.

## Operational Baseline

Milestone 26 closed the Operational Baseline / Trust Pass. The accepted proof used the Python module entrypoint from a disposable scratch root, ran `init`, `doctor`, `dashboard`, `task create`, `task run --worker shell`, workspace isolation checks, `task verify`, `task list`, `task show`, `promote-preview`, and `promote`, then confirmed the scratch task reached `promoted`. `result.txt` stayed out of the scratch root before promotion, existed under `.devflow/workspaces/task-0001/`, and appeared in the scratch root only after explicit promotion.

The proof originally failed because non-git copy-workspace promotion reused Git-only baseline and dirty-check guards. The closure repair keeps Git baseline/dirty checks for Git projects, keeps extra confirmation for deletion-applying and Git-native promotions, and allows default copy-workspace promotion in non-git scratch projects after verification and promotion preview.

The next safe product direction is aggressive local automation with hard stops: preserve the operational baseline, make verification evidence easy to find, expose concrete task controls in the operating layer, and use `devflow loop` where it removes babysitting from routine DevFlow-native work. Do not jump directly to provider-backed task-run adapters, hidden autonomous routing, databases, auto-resume without clear state, ungated auto-promotion, push/PR/publication automation, or new worker capability. If a later milestone moves toward non-shell workers, begin with architecture/contract alignment, registry loading/list/show/packet surfaces, manual adapter and shell alignment, deterministic task-fit/context estimation, and context pack building before any local/OpenAI-compatible/native provider adapter.


## Milestone 1 Checkpoint: Shell-Worker Control Room Completed

The first production-ready milestone of the Dev-Flow control plane is officially complete and checkpointed.

* **Checkpoint Commit**: `0dffab6 feat: add task log command`
* **Test Status**: 184 tests passing cleanly (6 skipped)

### Compact Checklist of Accepted Capabilities

- [x] **Task Creation**: `devflow task create` scaffolds task folders under `.devflow/tasks/` and handles dirty-git state copying safely.
- [x] **Isolated Workspaces**: Commands run strictly inside isolated workspaces under `.devflow/workspaces/<task_id>/` without mutating the main checkout.
- [x] **Shell Task Execution**: `devflow task run <task_id> --worker shell -- <command>` executes and captures command outcomes.
- [x] **Worker Command Persistence**: Stores exact run command strings (`worker_command`) shell-safely.
- [x] **Exit-Code & Timeout Propagation**: Propagates subprocess outcomes and respects customizable task execution timeouts.
- [x] **Verification Command Persistence**: Captures and persists the shell command string used for task verification.
- [x] **Verification Exit-Code Propagation**: Tracks and persists verification outcomes (`passed` / `failed`) and exit codes.
- [x] **Lifecycle Visibility**:
  - `devflow task list` provides status, updates, and compact verification states.
  - `devflow task show <task_id>` exposes comprehensive lifecycle details, events, readiness, and next-action hints.
- [x] **TaskPacket Projections**: `devflow task packet <task_id>` generates a deterministic JSON task context packet with virtualized paths (e.g. `<workspace>`, `<task>`) and secret redaction.
- [x] **Read-Only Log Viewing**: `devflow task log <task_id> [--verify] [--tail N]` prints raw worker or verification logs directly to stdout without mutating task state.

---

### Data Surface Architecture

To ensure strict engineering discipline, the data surface is stratified as follows:

#### 1. Canonical State (Source of Truth)
- `task.yaml`: Canonical current state and metadata.
- `events.jsonl`: Append-only, timeline-exact sequence of events.
- `questions.jsonl`: Formatted user-worker questions (when present).
- `verification.json`: Authoritative verification summary output.
- `logs/worker.log` & `logs/verify.log`: Raw terminal outputs representing absolute evidence of execution.

#### 2. Derived State (Non-Canonical/Cache-Only)
- `result.md`: Human-readable summary formatted by the worker or verification commands.
- `summary.json`: Local cache of parsed data derived entirely from canonical state.
- `packet.json`: Generated TaskPacket dump written instantly before worker executions.
- *TaskPacket projections*: Any dynamic context structure derived from canonical properties.
- *Review Capsule output*: A read-only rendered review view printed to the terminal; optional markdown export only with `task capsule --export-md`.

---

### Non-MVP Boundaries (Strictly Excluded)

The following areas are out-of-scope for the completed MVP and deferred:
* **Replaceable AI Adapters**: No Codex, Aider, or Hermes adapters.
* **Model Routing**: No dynamic LLM gateway routing or scheduling.
* **Dashboard / Web Server**: No database-driven dashboard, standalone marketing UI, or autonomous browser mutation surface. The approved local operating layer is the current browser-friendly control surface over derived filesystem evidence, with browser mutations limited to approved idea capture, idea parking, idea archive, task creation, shell worker execution, task verification, and task promotion.
* **Databases**: Relies strictly on plain filesystem architecture; no SQL/NoSQL databases.
* **Remote Publication / PR Automation**: No automatic push, pull request creation, or remote publication. Local loop-controlled promotion is allowed only through the explicit DevFlow gates above.

### Dogfooding Requirement

Future implementation slices should use Dev-Flow shell tasks or local worker commands where practical. This is required dogfooding for task isolation, logs, verification evidence, dashboard visibility, promotion previews, and handoff quality. It must not be used as justification to add provider-backed task-run adapters, autonomous routing, scheduling, or old workflow machinery before the shell-worker and manual proof-agent loop stays stable.

Run `devflow dogfood run --suite production-readiness` as the lightweight milestone readiness harness when changing the control-room pipeline. Silver is the current local readiness gate; lower scores should drive the smallest real improvement rather than weaker cases. Operating-layer changes must preserve the visual QA case, including desktop/mobile evidence, no-overflow checks, guided first viewport, active work cards, approval states, Advanced Commands, and current/baseline status.

Before tagging, building, or calling a milestone ship-ready, run `devflow release readiness --pytest-evidence <pytest-log> --stale-context-evidence <stale-context-log>` against a clean checkpoint after full pytest, production-readiness dogfood, operating-layer visual QA, and stale-context search evidence have been captured.

---

### Next Phase Outlook

Future adapter development may only begin using this stable checkpoint and [docs/architecture/agent-registry-and-adapter-runtime.md](architecture/agent-registry-and-adapter-runtime.md) as boundaries. The next phase must strictly preserve:
1. **Local-First State**: Rely on plain-file source of truth before any database storage.
2. **Workspace Isolation**: Ensure replaceable workers operate strictly within copied sandboxes.
3. **Verification Ownership**: Control-plane holds authoritative ownership of verification execution.
4. **Gated Promotion**: Keep manual promotion available and allow local loop promotion only when durable policy, run flags, verification, preview, and blocker checks all agree.
