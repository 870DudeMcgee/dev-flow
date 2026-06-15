# Current Control-Room Product Contract

Status: active, reconciled on 2026-06-15.

This is the stable contract for the current Dev-Flow control-room milestone. It freezes the shell-worker, manual proof-agent, local Ollama evidence wrapper, visibility, verification, passive review-readiness, explicit goal lifecycle, bounded freshness dispatch, simple scheduler projection, explicit scheduler retry requests, explicit question answer/resolve evidence, and human-controlled promotion behavior that docs and tests should agree on. Implemented transition layers are allowed only as explicit read-only, local-evidence, or manual planning aids until promoted.

Post-MVP worker adapter boundaries are described in [docs/adapter-contract.md](adapter-contract.md). The opt-in Git-native worker isolation and promotion slice is described in [docs/architecture/git-native-worker-isolation-and-promotion.md](architecture/git-native-worker-isolation-and-promotion.md). The registry/provider/role architecture is described in [docs/architecture/agent-registry-and-adapter-runtime.md](architecture/agent-registry-and-adapter-runtime.md), with task-fit/context routing evidence design in [docs/architecture/agent-selection-and-context-routing.md](architecture/agent-selection-and-context-routing.md). Pre-conditions, state transitions, and verification invalidation rules for applied patches are documented in [docs/architecture/patch-application-and-readiness-gating.md](architecture/patch-application-and-readiness-gating.md).

The stable runtime now includes an opt-in Git-native shell-worker slice through `devflow task create --git-worktree`. The default task path remains copy-workspace. It also includes `devflow task local` as a legacy local Ollama advisory wrapper for Qwen/Qwopus/Gemma planning, scouting, and review output; it is not a router, auto-editor, patch-applier, verification runner, or promotion path. The narrow registry-backed local patch runtime is `devflow task run <task-id> --worker qwopus-implementer` or `devflow task run <task-id> --worker gemma4-12b-qat-implementer` when explicit local-agent selection evidence identifies an installed eligible Gemma profile. These routes write patch evidence for Dev-Flow to review, dry-run, apply, and verify. The simple scheduler runtime is a derived projection over existing task, freshness, goal, question, lock, worker, and verification evidence; it does not launch work, verify work, promote work, or route to providers. The question loop lists and shows derived worker/blocker questions, then writes human answer or resolve records only when explicitly commanded; it recommends resume commands without executing them.

## Stable Commands

```bash
devflow --help
devflow init
devflow doctor
devflow reconcile
devflow dashboard
devflow status --json
devflow supervisor policy
devflow supervisor policy --json
devflow supervisor packet
devflow supervisor packet --json
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
devflow hermes imessage-check --json
devflow map init
devflow map show
devflow map check
devflow task --help
devflow task create "example task"
devflow task create --project factory-scheduler "example task"
devflow task create --git-worktree "example git task"
devflow task run <task-id> --worker shell -- /bin/sh -c "echo hello > result.txt"
devflow task run <task-id> --project factory-scheduler --worker shell -- /bin/sh -c "echo hello > result.txt"
devflow task run <task-id> --shell "echo hello > result.txt"
devflow task run <task-id> --worker qwopus-implementer
devflow task run <task-id> --worker gemma4-12b-qat-implementer
devflow task review-patch <task-id>
devflow task review-patch <task-id> --project factory-scheduler
devflow task review-patch <task-id> --agent qwopus-implementer
devflow task review-patch <task-id> --agent gemma4-12b-qat-implementer
devflow task patch-dry-run <task-id>
devflow task patch-dry-run <task-id> --project factory-scheduler
devflow task patch-dry-run <task-id> --agent qwopus-implementer
devflow task patch-dry-run <task-id> --agent gemma4-12b-qat-implementer
devflow task apply-patch <task-id> --agent qwopus-implementer
devflow task apply-patch <task-id> --agent gemma4-12b-qat-implementer
devflow task apply-patch <task-id> --project factory-scheduler --agent qwopus-implementer
devflow task apply-patch <task-id> --run-id <run-id>
devflow task verify <task-id> --shell "test -f result.txt"
devflow task verify <task-id> --project factory-scheduler --shell "test -f result.txt"
devflow task local <task-id> --agent qwen-planner
devflow task local <task-id> --agent qwopus-implementer
devflow task local <task-id> --agent gemma-reviewer --input-worker qwopus-implementer
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
devflow task show <task-id>
devflow task show <task-id> --project factory-scheduler
devflow task review <task-id>
devflow task review <task-id> --json
devflow task review <task-id> --project factory-scheduler
devflow task next-action <task-id>
devflow task next-action <task-id> --json
devflow task next-action <task-id> --project factory-scheduler
devflow task review-ready
devflow task review-ready --json
devflow task review-ready <task-id> --json
devflow task review-ready <task-id> --project factory-scheduler --json
devflow task capsule <task-id>
devflow task capsule <task-id> --project factory-scheduler
devflow task packet <task-id>
devflow task packet <task-id> --project factory-scheduler
devflow task log <task-id>
devflow task log <task-id> --project factory-scheduler
devflow task orchestrate <task-id> --plan-only
devflow worker validate-outcome <path-to-outcome-json>
devflow knowledge capture --from-task <task-id>
devflow knowledge capture --from-validation <path-to-validation-json>
devflow knowledge list
devflow knowledge show <knowledge-id>
devflow knowledge promote <knowledge-id>
devflow knowledge reject <knowledge-id>
devflow knowledge search "<query>"
devflow idea capture "raw idea"
devflow idea list
devflow idea show <idea-id>
devflow idea classify <idea-id> --maturity goal_ready
devflow idea promote <idea-id> --to goal --rationale "human reviewed"
devflow idea create-goal <idea-id> --dry-run
devflow idea create-goal <idea-id>
devflow idea create-task <idea-id> --dry-run
devflow idea create-task <idea-id>
devflow idea archive <idea-id> --reason "superseded"
devflow goal init <goal-id> --from <brief.md>
devflow goal list
devflow goal show <goal-id>
devflow goal status <goal-id>
devflow goal next <goal-id>
devflow goal slices <goal-id>
devflow goal activate <goal-id> --reason "ready to execute"
devflow goal pause <goal-id> --reason "waiting on review"
devflow goal block <goal-id> --reason "needs human answer"
devflow goal complete <goal-id> --reason "all task slices promoted and reviewed"
devflow goal archive <goal-id> --reason "superseded"
devflow dogfood list
devflow dogfood show <case-id>
devflow dogfood run --suite production-readiness
devflow dogfood score <run-id>
devflow dogfood report <run-id>
devflow task promote-preview <task-id>
devflow task promote-preview <task-id> --project factory-scheduler
devflow task promote <task-id>
devflow task promote <task-id> --project factory-scheduler
devflow task close <task-id> --outcome rejected --reason "superseded by manual repair"
devflow task cleanup <task-id> --preview
devflow task cleanup <task-id> --apply
devflow task cleanup <task-id> --dry-run
devflow task prune-closed --preview --older-than 30d
devflow task prune-closed --apply --older-than 30d
devflow worktree list
devflow worktree prune --dry-run
devflow branch list
devflow branch archive <branch> --dry-run
devflow agent show devflow-manual-codex-worker
devflow agent list --json
devflow agent show local-qwopus-inspector --json
devflow agent policy --json
devflow agent context-pack <task-id> qwopus-implementer --role implementation_worker --json
devflow agent evidence <task-id> --json
devflow agent discover-local --json
devflow agent select-local <task-id> --role implementation_worker --json
devflow agent run --task <task-id> --profile local-qwopus-inspector --dry-run --json
devflow agent run --task <task-id> --profile local-qwopus-inspector --json
devflow agent packet <task-id> devflow-manual-codex-worker
devflow task run <task-id> --worker devflow-manual-codex-worker
```

## Implemented But Experimental Transition Commands
The following CLI commands remain experimental and restricted to read-only/manual planning/auditing aids:

```bash
devflow agent packet <task-id> <non-proof-agent-id>
devflow task pack <task-id> <role>
```

### Command Maturity Classifications

To guarantee execution safety and prevent automated agents from operating on unstable transition layers, all CLI commands are classified under a strict maturity hierarchy:

- **Stable**: Authorized local control-room commands (e.g., `init`, `doctor`, `reconcile`, `dashboard`, `status --json`, `supervisor policy`, `supervisor packet`, `hermes imessage-check --json`, `map init`, `map show`, `map check`, `task create`, `task list`, `task show`, `task review`, `task next-action`, `task review-ready`, `task capsule`, `task run`, `task verify`, `task local`, `task fit`, `task scout`, `task route`, `task scorecard`, `task packet`, `task log`, `task orchestrate --plan-only`, `worker validate-outcome`, `knowledge capture/list/show/promote/reject/search`, `idea capture/list/show/classify/promote/create-goal/create-task/archive`, `goal init/list/show/status/next/slices/activate/pause/block/complete/archive`, `dogfood list/show/run/score/report`, `task promote-preview`, `task promote`, `task cleanup`, `worktree list`, `worktree prune`, `branch list`, `branch archive`, `agent show devflow-manual-codex-worker`, `agent list --json`, `agent show <profile-id> --json`, `agent policy --json`, `agent context-pack`, `agent evidence`, `agent discover-local --json`, `agent select-local <task-id> --role <role> --json`, `agent run --task <task-id> --profile <profile-id> --dry-run --json`, `agent run --task <task-id> --profile <profile-id> --json`, `agent packet <task-id> devflow-manual-codex-worker`).
- **Experimental-ReadOnly**: Read-only diagnostic and context-assembly aids (e.g., `context`, `task pack`, non-proof-agent registry inspection).
- **Experimental-Manual**: Manual coordination and polling harnesses (e.g., `supervise`).
- **Forbidden-Runtime**: Any command or background process that bypasses human review, routes models automatically, or mutates the main checkout autonomously. No such commands are allowed in the control room.

Agent adapters also carry runtime maturity: `stable_runtime`, `local_patch_runtime`, `experimental_readonly`, or `planned_not_executable`. Only `shell` and `manual` are `stable_runtime` executable adapters in this milestone. `ollama_chat` is executable as a safe `local_patch_runtime` patch agent such as `qwopus-implementer` or `gemma4-12b-qat-implementer`, or as a read-only local worker-pool evidence profile such as `local-qwopus-inspector`: provider `ollama`, loopback base URL, no shell, no arbitrary network permission, and `can_promote: false`. Remote provider adapters may appear in registries or docs, but task execution must fail clearly if they are invoked.

Experimental context, task pack, and the legacy `supervise` loop are hidden from `--help` by default and refuse execution unless the environment variable `DEVFLOW_EXPERIMENTAL=1` is explicitly set. The read-only `supervisor policy` and `supervisor packet` surfaces are visible because they are part of this stable milestone. The proof-agent registry commands are visible for the same reason.

`devflow init` creates or repairs the local control-room seed structure. `devflow doctor` checks that structure. `devflow reconcile` reports crash/interruption evidence without mutating files, including partial task/system event writes, task/system event divergence, interrupted promotion evidence, and inconsistent task artifacts. `devflow dashboard` renders the current text-only terminal dashboard from task artifacts. `devflow status --json` emits a read-only, machine-readable control-room summary for humans and supervisor agents.

`devflow map init`, `devflow map show`, and `devflow map check` manage the optional root `CODE_MAP.md` orientation artifact. `map init` scaffolds a human-authored template, `map show` prints the current map, and `map check` validates required sections plus entry-point paths. These commands do not generate maps from source, route tasks, call providers, mutate task state, or make promotion decisions. When `CODE_MAP.md` exists, `devflow task packet` may include a bounded read-only excerpt for worker orientation.

`devflow project create/import/list/show/status/doctor/archive/remove/connect-github`, `devflow dashboard --all-projects`, and `devflow status --all-projects --json` operate on the global project registry as an index while each project-local `.devflow/` remains authoritative. Missing active project paths are human-decision items: run `devflow project doctor <project-id>` first, then explicitly repair/import the real root, archive intentionally retired projects with `devflow project archive <project-id>`, or remove junk records with `devflow project remove <project-id> --registry-only`. Archived projects are hidden from default project lists and all-project scans but remain visible with `project list --include-archived`. Read-only all-project surfaces report missing paths and next actions; they do not recreate, archive, remove, publish, push, route models, or call providers.

`devflow task create` creates the task artifacts and task workspace needed by the later commands. By default, task files live under the current working directory's `.devflow/tasks/`. `devflow task create --project <project-id>`, `devflow task list --project <project-id>`, `devflow task show <task-id> --project <project-id>`, `devflow task run <task-id> --project <project-id>`, `devflow task verify <task-id> --project <project-id>`, `devflow task packet <task-id> --project <project-id>`, `devflow task review <task-id> --project <project-id>`, `devflow task next-action <task-id> --project <project-id>`, `devflow task review-ready [<task-id>] --project <project-id>`, `devflow task capsule <task-id> --project <project-id>`, `devflow task log <task-id> --project <project-id>`, `devflow task review-patch <task-id> --project <project-id>`, `devflow task patch-dry-run <task-id> --project <project-id>`, `devflow task apply-patch <task-id> --project <project-id>`, `devflow task promote-preview <task-id> --project <project-id>`, and `devflow task promote <task-id> --project <project-id>` resolve the registered project root and use that project's `.devflow/tasks/` and `.devflow/workspaces/` instead. Task IDs are project-local; cross-project refs are displayed as `<project_id>:<task_id>`. Shell worker commands and verification commands run from the task workspace. The preferred shell-worker invocation is `devflow task run <task-id> --worker shell -- <command>`; `--shell "<command>"` remains supported.

`devflow task local <task-id> --agent qwen-planner`, `devflow task local <task-id> --agent qwopus-implementer`, and `devflow task local <task-id> --agent gemma-reviewer --input-worker qwopus-implementer` compose prompts from `task.yaml`, Dev-Flow rules, workspace/context listings, and selected prior local-worker output, then call `ollama run <model>` through a local subprocess with a 600-second default timeout. Raw output is captured as advisory evidence only; Dev-Flow does not parse it as truth, write `proposal.patch`, apply it, verify it, commit it, merge it, route automatically, or call remote provider APIs.

`devflow task run <task-id> --worker qwopus-implementer` builds a bounded agent packet, calls local Ollama through `/api/generate` with `qwopus:latest`, preserves raw output under `.devflow/tasks/<task-id>/agents/qwopus-implementer/raw_output.md`, writes `.devflow/tasks/<task-id>/agents/qwopus-implementer/proposal.patch` when a unified diff is present, and records inspectable `run.json` plus `result.md` summaries. `devflow task run <task-id> --worker gemma4-12b-qat-implementer` uses the same evidence-only local patch contract with native Ollama `/api/chat`, thinking disabled, and explicit bounded generation settings when local selection evidence identifies that installed profile. These are canonical local patch proposal paths, not proof of correctness. The model does not edit main, promote, or verify. The human-controlled path is `devflow task show <task-id>`, `devflow task review-patch <task-id> --agent <agent-id>`, `devflow task patch-dry-run <task-id> --agent <agent-id>`, `devflow task apply-patch <task-id> --agent <agent-id>`, then `devflow task verify`, `devflow task promote-preview`, and `devflow task promote`. If a local patch worker fails or produces no usable patch, `devflow task escalation-packet <task-id> --agent <agent-id>` writes a compact copy-paste packet from local evidence only; it does not call remote providers.

`devflow agent context-pack <task-id> <agent-id> --role <role> --json` writes role-scoped context-pack evidence under `.devflow/tasks/<task-id>/context-packs/` from canonical TaskPacket data. It is derived, disposable context evidence, not canonical task state and not routing authority. `devflow agent evidence <task-id> --json` reads existing shell, manual proof-agent, local patch, and local model evidence and returns a compact derived summary without mutating task state.

`devflow agent discover-local --json` inventories installed local Ollama models and derives conservative capability profiles from local manifests. `devflow agent select-local <task-id> --role <role> --json` ranks installed registry agents for the explicit role and writes `.devflow/tasks/<task-id>/agent-selection.json`. This is the current model-agnostic selection boundary: Dev-Flow chooses the best eligible installed profile for the requested role from registry policy and manifest evidence. It does not autonomously pick a model for arbitrary tasks, run the selected worker, create registry entries for unregistered models, verify, promote, merge, push, or call remote providers.

The task-fit/context-routing evidence form writes derived artifacts only. It classifies task fit, context size, scout signals, candidate eligibility, rejected candidates, unresolved roles, and post-run quality signals. It does not run workers, call remote providers, silently substitute models, verify, promote, commit, push, or create pull requests.

`devflow agent run --task <task-id> --profile local-qwopus-inspector --dry-run --json` previews the read-only local model worker-pool path without calling a model or writing evidence. `devflow agent run --task <task-id> --profile local-qwopus-inspector --json` is the first real WorkerEvidence slice: it builds a bounded task packet, calls the configured local OpenAI-compatible/Ollama endpoint through `local_model_client.py`, writes `.devflow/tasks/<task-id>/local-model-runs/<run-id>/run.json`, `packet.md`, `response.md`, `raw_output.txt`, and optional `error.txt`, then stops. Gemma summarizer profiles may use native Ollama `/api/chat` with explicit context and thinking disabled when the manifest/template requires it. It does not edit source files, write `proposal.patch`, apply patches, verify, commit, merge, push, promote, or mutate canonical task state.

`devflow task review-patch <task-id>` and `devflow task patch-dry-run <task-id>` operate on normalized local-model run proposal evidence under `.devflow/tasks/<task-id>/local-model-runs/<run-id>/`. With `--project <project-id>`, they resolve the registered project root before reading agent proposal evidence or writing patch-review/dry-run evidence, and stored next-action commands remain project-scoped. The `--agent <agent-id>` form first normalizes that agent's `proposal.patch` into a matching local-model run evidence folder. Patch review writes `patch-review.json` and `patch-review.md`. Patch dry-run reads `proposal.patch` and `patch-review.json`, inspects the isolated task workspace, writes `patch-dry-run.json` and `patch-dry-run.md`, and does not apply patches, modify source/workspace files, verify, stage, commit, call models, call network APIs, or promote. `devflow task apply-patch` refuses mutation unless the selected patch has matching fresh acceptable patch review and dry-run evidence in the resolved project root. The full staged contract and gating mechanics are documented in [docs/architecture/patch-evidence-ladder.md](architecture/patch-evidence-ladder.md) and [docs/architecture/patch-application-and-readiness-gating.md](architecture/patch-application-and-readiness-gating.md).

`devflow task next-action <task-id>`, `devflow task review <task-id>`, and `devflow task review-ready [<task-id>]` are read-only supervisor-safe task inspection surfaces. `next-action` derives one recommended safe next action from `task.yaml`, patch evidence, verification evidence, promotion-preview evidence, and closure metadata. `review` renders a compact capsule with task identity, worker/lane, current state, changed files when known, patch proposal/review/dry-run/application status, verification status, promotion-preview status, Git/worktree facts, evidence paths, risks, safe commands, human-approval commands, and forbidden bypass actions. `review-ready` classifies active tasks as `ready_for_review`, `needs_verification`, `verification_failed`, `needs_promotion_preview`, `blocked`, `worker_failed`, `running`, or `not_ready`; includes concrete blockers, evidence paths, a deterministic sorting score, and the safest next command; and refuses to mark a task ready when canonical verification or promotion-readiness evidence is malformed, stale, or missing. These commands tolerate missing optional artifacts, distinguish unknown from failed, and never run workers, apply patches, verify, promote, mutate task state, create review files, route models, or call providers.

`devflow supervisor policy` outputs the versioned supervisor/Hermes operating policy, including the external operator boundary, command classes, path authority, and forbidden actions. `devflow supervisor packet` outputs one compact read-only packet with project identity, repo root, branch/cleanliness, counts, active tasks, review queue, blocked or failed tasks, stale/conflicted tasks, preview-ready tasks, promotion-ready tasks, next safe actions, policy summary, human-approval commands, forbidden actions, evidence paths, warnings, suggested command lists, and timestamp. `devflow supervisor route-message "<raw Telegram text>" --json` classifies lightweight Telegram/Hermes text into a visible route, model or task action, safety action, reason, footer, and optional `operator_plan.pending_action` without running commands, calling models, creating tasks, or mutating state. Hermes may store and execute only that exact pending action after explicit Telegram approval. `devflow hermes imessage-check --json` is a read-only readiness probe for platform/app/config/CLI presence; it does not read messages, inspect `chat.db`, send messages, or require Full Disk Access. Hermes, Codex, Antigravity, and other supervisor agents must treat these as derived views over Dev-Flow artifacts, not a second source of truth. The Hermes operator contract and command allowlist are documented in [docs/integrations/hermes-operator-layer.md](integrations/hermes-operator-layer.md), [docs/integrations/hermes-command-allowlist.md](integrations/hermes-command-allowlist.md), [docs/integrations/hermes-imessage-exploration.md](integrations/hermes-imessage-exploration.md), and [docs/integrations/hermes-local-parallelism.md](integrations/hermes-local-parallelism.md).

`devflow git status`, `devflow git checkpoint`, `devflow sync-main`, and `devflow push-main` are Git guardrail surfaces. `git status` is read-only and reports DevMode presence plus branch, dirty, operation-in-progress, origin/main, promotion, and push safety. `git checkpoint --message "<message>"` previews an explicit local checkpoint; with `--yes`, it stages all unignored changes and commits only when `main` is safe, origin is not ahead/diverged, no Git operation is in progress, and no conflicts are present. It does not push, promote, merge, or open a PR. `sync-main` fetches origin and fast-forwards `main` only. `push-main` pushes `main` only when the local checkout is clean and `origin/main` is not ahead or diverged.

`devflow task promote-preview` and `devflow task promote` are explicit, human-controlled promotion surfaces. Promotion preview reports the task baseline commit, the current main checkout HEAD, and whether the baseline is unchanged, changed, or unavailable. `devflow task promote-preview <task-id> --project <project-id>` is read-only and resolves the registered project root before inspecting task workspace changes. `devflow task promote <task-id> --project <project-id>` resolves the registered project root, preserves the existing human confirmation and promotion safety gates, and applies approved changes to that project root instead of the caller's current directory. Git-native promotion preview also reports origin/main freshness and conflict prediction. Promotion is not automatic and does not stage, push, open a pull request, bypass verification readiness checks, or promote work from a stale task baseline unless the human explicitly passes `--force-stale-baseline` after reviewing the risk.

`devflow task capsule <task-id>` renders a read-only Review Capsule from existing evidence. It summarizes task identity, status, worker, workspace/worktree, Git branch and latest commit when available, verification result, promotion-preview readiness, changed files, and inline previews for small changed text files. It labels missing evidence, truncates large text files, refuses absolute paths and `..` traversal, never reads outside the resolved task workspace/worktree, and never dumps binary files. `task run`, `task verify`, `task finalize`, and `task promote-preview` print the capsule after their normal output when current evidence is available. The capsule is a rendered view, not canonical state; it does not mutate task status, promote, close, weaken gates, or create markdown files by default. `--project <project-id>` resolves the registered project root before rendering; `--export-md` may write one explicit `.devflow/tasks/<task-id>/review-capsule.md` export only when requested.

`devflow task orchestrate <task-id> --plan-only` writes `.devflow/tasks/<task-id>/orchestration-plan.yaml` as policy evidence. It records Git baseline/freshness assumptions, DevMode requirements, allowed worker roles, context layers, write boundaries, required evidence, stop conditions, and promotion rules. It is plan-only: it does not execute workers or providers, apply patches, verify code, mutate main, route models autonomously, or promote.

`devflow worker validate-outcome <path-to-outcome-json>` validates worker outcome metadata and writes validation evidence under the task folder when possible, otherwise under `.devflow/outcome-validations/`. It rejects malformed JSON, missing fields, unknown source/outcome/tool statuses, unsafe touched paths, task-id mismatches, and outcomes that need human review but do not declare it. It does not run agents, apply patches, verify code, promote tasks, route models, or mutate `task.yaml`.

`devflow knowledge capture`, `knowledge list`, `knowledge show`, `knowledge promote`, `knowledge reject`, and `knowledge search` manage local Knowledge Foundry notes under `.devflow/knowledge/`. Capture creates proposed notes only from existing task or validation evidence; promotion/rejection changes knowledge status only and is separate from task promotion. This is human-reviewed knowledge curation, not ML training, hidden agent memory, vector search, RAG, or automatic task/goal creation.

The Idea Foundry form is `devflow idea capture/list/show/classify/promote/create-goal/create-task/archive`. It stores project-local intake evidence under `.devflow/ideas/<idea-id>/`, keeps raw ideas separate from goals and tasks until an explicit bridge command is run, and records human classification and promotion decisions. `devflow idea create-goal` and `devflow idea create-task` require prior matching human promotion evidence, write bidirectional idea-to-goal/task links, and create Dev-Flow state only. Idea creation commands do not run workers, call providers, verify, promote code, commit, push, open pull requests, or route models.

`devflow dogfood run --suite production-readiness` runs deterministic local production-readiness cases and writes `.devflow/dogfood/runs/<run-id>/run.yaml`, `scorecard.yaml`, `report.md`, and per-case `case-result.yaml` evidence. The suite measures safety, pipeline correctness, context efficiency, worker artifact quality, recovery handling, knowledge capture, operating-layer visual QA, and lightweight behavior. It reuses existing task, orchestration, worker outcome validation, verification, promotion-readiness, knowledge, and operating-layer visual QA surfaces, then closes any task records it created with the `evidence-only` outcome so dogfood evidence does not remain in the active project queue. The visual QA case accepts deterministic fallback PNG/SVG evidence as the minimum, external/Appshot PNG drop-ins when present, and optional Playwright browser rasters when available. It does not execute providers, route autonomously, promote, push, create a database, create a dashboard, run a daemon, use vector search/RAG/embeddings, or train models. Silver is the default pass gate for the production-readiness run.

`devflow task close` marks a task inactive without deleting evidence. It requires an explicit outcome and reason, writes `.devflow/tasks/<task-id>/closure.json`, appends a close event, and preserves logs, proposal patches, verification, finalization, and promotion artifacts. `devflow task show` and `devflow task list` surface closed tasks with their outcome. `devflow task cleanup <task-id> --preview` refuses active tasks, reports conservative task-owned runtime cleanup candidates, and deletes nothing. `--apply` reruns the same safety analysis, removes only safe `.devflow/workspaces/<task-id>` or `.devflow/worktrees/<task-id>/<worker>` runtime targets, writes `cleanup.json`, and appends cleanup evidence. The older `--dry-run` spelling remains a compatibility preview for existing Git-native cleanup reporting.

`devflow task prune-closed --preview --older-than <duration>` is the separate evidence-retention path. It scans task records, reports closed-task evidence directories under `.devflow/tasks/` that are older than the requested duration, and writes an audit record under `.devflow/prune-runs/<run-id>.json` without deleting anything. `--apply` repeats the same safety checks and deletes only eligible closed-task evidence directories under `.devflow/tasks/<task-id>/`. It refuses active tasks, closed tasks without valid `closure.json` metadata, symlinked or path-traversal task evidence paths, and anything whose resolved path is outside `.devflow/tasks/`. Cleanup removes runtime artifacts; prune-closed removes retained closed-task evidence only after explicit approval.

`devflow agent show devflow-manual-codex-worker` displays the stable proof-agent contract:

- Agent ID: `devflow-manual-codex-worker`
- Role: `implementation_worker`
- Adapter: `manual`
- Execution mode: `human_launched_agent`
- Purpose: consume a bounded task packet, edit only the assigned isolated workspace, produce structured result, question, or failure evidence, then stop.

`devflow agent packet <task-id> devflow-manual-codex-worker` prints a bounded packet with role, allowed reads, allowed writes, forbidden writes, required outputs, completion rules, and Codex-ready manual instructions.

`devflow task run <task-id> --worker devflow-manual-codex-worker` creates `.devflow/tasks/<task-id>/agents/devflow-manual-codex-worker/handoff.md` and packet evidence for a human-launched Codex or IDE agent, then leaves the task blocked with `manual_agent_state: awaiting_human`. It does not call a provider API, choose a model, schedule another agent, verify work, promote work, or mutate the main checkout. Pressing Enter in an interactive terminal is not completion evidence.

## Stable Filesystem Artifacts

For a created task, the MVP contract is:

```text
.devflow/tasks/<task-id>/task.yaml
.devflow/tasks/<task-id>/.lock/owner.json   # live only during task-local mutations
.devflow/tasks/<task-id>/events.jsonl
.devflow/tasks/<task-id>/verification.json
.devflow/tasks/<task-id>/closure.json
.devflow/tasks/<task-id>/cleanup.json
.devflow/tasks/<task-id>/orchestration-plan.yaml
.devflow/tasks/<task-id>/worker-outcome-validation.json
.devflow/tasks/<task-id>/logs/worker.log
.devflow/tasks/<task-id>/logs/verify.log
.devflow/tasks/<task-id>/patch-application.json
.devflow/tasks/<task-id>/patches/<patch-hash>.json
.devflow/tasks/<task-id>/agents/devflow-manual-codex-worker/handoff.md
.devflow/tasks/<task-id>/agents/devflow-manual-codex-worker/result.md
.devflow/prune-runs/<run-id>.json
.devflow/tasks/<task-id>/agents/devflow-manual-codex-worker/questions.jsonl
.devflow/tasks/<task-id>/agents/devflow-manual-codex-worker/worker_failed.json
.devflow/tasks/<task-id>/agents/qwopus-implementer/packet.json
.devflow/tasks/<task-id>/agents/qwopus-implementer/raw_output.md
.devflow/tasks/<task-id>/agents/qwopus-implementer/proposal.patch
.devflow/tasks/<task-id>/agents/qwopus-implementer/result.md
.devflow/tasks/<task-id>/agents/qwopus-implementer/run.json
.devflow/tasks/<task-id>/agents/qwopus-implementer/logs/worker.log
.devflow/tasks/<task-id>/agents/<local-patch-agent-id>/packet.json
.devflow/tasks/<task-id>/agents/<local-patch-agent-id>/raw_output.md
.devflow/tasks/<task-id>/agents/<local-patch-agent-id>/proposal.patch
.devflow/tasks/<task-id>/agents/<local-patch-agent-id>/result.md
.devflow/tasks/<task-id>/agents/<local-patch-agent-id>/run.json
.devflow/tasks/<task-id>/agents/<local-patch-agent-id>/logs/worker.log
.devflow/tasks/<task-id>/agents/<local-patch-agent-id>/logs/worker.log
.devflow/tasks/<task-id>/agent-selection.json
.devflow/tasks/<task-id>/context-packs/<role>-<agent-id>.json
.devflow/tasks/<task-id>/context-packs/<role>-<agent-id>.md
.devflow/tasks/<task-id>/context-packs/<role>-<agent-id>.packet.json
.devflow/tasks/<task-id>/local-model-runs/<run-id>/proposal.md
.devflow/tasks/<task-id>/local-model-runs/<run-id>/proposal.json
.devflow/tasks/<task-id>/local-model-runs/<run-id>/proposal.patch
.devflow/tasks/<task-id>/local-model-runs/<run-id>/patch-review.md
.devflow/tasks/<task-id>/local-model-runs/<run-id>/patch-review.json
.devflow/tasks/<task-id>/local-model-runs/<run-id>/patch-dry-run.md
.devflow/tasks/<task-id>/local-model-runs/<run-id>/patch-dry-run.json
.devflow/tasks/<task-id>/review-capsule.md                 # only with task capsule --export-md
.devflow/workspaces/<task-id>/
.devflow/workspaces/<task-id>/local-workers/<worker-name>/prompt.md
.devflow/workspaces/<task-id>/local-workers/<worker-name>/response.raw.md
.devflow/workspaces/<task-id>/local-workers/<worker-name>/response.md
.devflow/workspaces/<task-id>/local-workers/<worker-name>/run.json
.devflow/workspaces/<task-id>/local-workers/<worker-name>/stderr.log
.devflow/worktrees/<task-id>/shell/                          # only for --git-worktree tasks
.devflow/tasks/<task-id>/workers/shell/git.json              # only for --git-worktree tasks
.devflow/tasks/<task-id>/workers/shell/diff.patch            # only for --git-worktree tasks
.devflow/tasks/<task-id>/workers/shell/diff-summary.json     # only for --git-worktree tasks
.devflow/tasks/<task-id>/workers/shell/verification.json     # only for --git-worktree tasks
.devflow/tasks/<task-id>/workers/shell/promotion-preview.json # only for --git-worktree tasks
.devflow/outcome-validations/<name>-validation.json
.devflow/knowledge/<knowledge-id>/knowledge.json
.devflow/knowledge/<knowledge-id>/note.md
.devflow/knowledge/<knowledge-id>/events.jsonl
.devflow/ideas/<idea-id>/idea.json
.devflow/ideas/<idea-id>/raw.md
.devflow/ideas/<idea-id>/classification.md
.devflow/ideas/<idea-id>/promotion.md
.devflow/ideas/<idea-id>/goal-brief.md
.devflow/ideas/<idea-id>/task-brief.md
.devflow/ideas/<idea-id>/events.jsonl
.devflow/goals/<goal-id>/idea-link.yaml
.devflow/tasks/<task-id>/idea.md
.devflow/tasks/<task-id>/idea-link.yaml
.devflow/dogfood/cases/<case-id>.yaml
.devflow/dogfood/runs/<run-id>/run.yaml
.devflow/dogfood/runs/<run-id>/scorecard.yaml
.devflow/dogfood/runs/<run-id>/report.md
.devflow/dogfood/runs/<run-id>/cases/<case-id>/case-result.yaml
```

`task.yaml` is the canonical current task state. `events.jsonl` is append-only evidence. `verification.json` stores the latest verification result. Logs are raw command evidence. Patch application writes a SHA-256-addressed evidence artifact under `patches/` and updates latest `patch-application.json`; `patch_applied` events point at that evidence. The workspace is the only current place where shell-worker results and local Ollama worker artifacts are written. Versioned state artifacts include `schema_version: 1`; unversioned historical task files are treated as version 1, and unknown task schema versions are refused.

Mutating task operations use a task-local `.lock/` directory with `owner.json` metadata. `run`, `local`, `verify`, `apply-patch`, and `promote` refuse concurrent mutations for the same task, report the current lock owner, and recover locks that are stale beyond the lock TTL.

## Optional Derived State

`.devflow/tasks/<task-id>/summary.json` may exist as a derived cache for visibility and token efficiency. It is not canonical state. It may be deleted and regenerated without losing information. If it is missing, stale, malformed, or disagrees with `task.yaml`, `events.jsonl`, `verification.json`, or logs, the canonical files win.

`.devflow/tasks/<task-id>/packet.json` may exist as a generated TaskPacket dump. It is derived state and is written immediately before a worker execution when needed. Dynamic TaskPacket projections are also derived state.

`.devflow/tasks/<task-id>/result.md` may exist as a human-readable result summary. It is not canonical state.

`.devflow/tasks/<task-id>/review-capsule.md` may exist only after an explicit `devflow task capsule <task-id> --export-md`. It is a point-in-time export of a rendered review view and is never created by default.

`.devflow/tasks/<task-id>/orchestration-plan.yaml` is plan-only policy evidence. `.devflow/tasks/<task-id>/worker-outcome-validation.json` and `.devflow/outcome-validations/*.json` are metadata validation evidence. `.devflow/knowledge/<knowledge-id>/` stores human-reviewed knowledge curation records. `.devflow/ideas/<idea-id>/` stores human-reviewed idea intake records. None of these files override canonical task state or promotion readiness.

Manual proof-agent evidence under `.devflow/tasks/<task-id>/agents/devflow-manual-codex-worker/` is worker-produced evidence, not canonical task state. Dev-Flow may display `awaiting_human`, `blocked`, `failed`, and `result_present` in `task show` and `dashboard`, but only Dev-Flow updates `task.yaml`, `events.jsonl`, `verification.json`, merge-readiness, and promotion state.

## Stable Safety Rules

- Shell workers execute only in `.devflow/workspaces/<task-id>/`.
- Local Ollama workers write evidence only under `.devflow/workspaces/<task-id>/local-workers/<worker-name>/`.
- Verification commands execute only in `.devflow/workspaces/<task-id>/`.
- Tampered task workspace paths are refused before command execution.
- Symlinks are skipped during scratchpad copy.
- Shell-worker results do not write into the main checkout.
- Local Ollama worker success is based only on subprocess exit code `0`; nonempty model output with a nonzero exit remains failed evidence.
- Local Ollama workers do not auto-edit files, auto-verify, auto-commit, auto-merge, or auto-promote.
- Promotion to the main checkout is explicit, human-confirmed, and gated on verification readiness.
- Promotion refuses unsafe workspace paths and blocks dirty main-checkout changes unless explicitly forced.
- New task events are hash-chained with monotonic indexes, previous-event hashes, and current-event hashes; `doctor` reports malformed or edited task event logs.
- `doctor --strict` is read-only and reports stale task locks, unsafe workspace paths, malformed or inconsistent JSON artifacts, missing worker/verification logs, malformed manual-agent evidence, missing patch evidence, promoted-task consistency, and Git-native worker branch sharing across tasks.
- `devflow reconcile` is read-only and reports partial task/system event writes, task/system event divergence, interrupted promotion evidence, and inconsistent task artifacts.
- No SQLite database is created.
- Default copy-workspace tasks do not create `.devflow/worktrees/`; `--git-worktree` tasks do.
- Legacy agent, memory, DAG, trace, worktree, database, and software-factory systems remain bypassed for this MVP path.
- Manual proof-agent workers may write only to the assigned isolated workspace and their agent evidence directory.
- Manual proof-agent completion does not imply verification or promotion readiness.
- Orchestration planning is `--plan-only`; it records policy evidence and never schedules providers, runs workers, applies patches, verifies, promotes, or changes main.
- Worker outcome validation validates metadata only; it does not treat worker claims as proof of correctness and never mutates canonical task state.
- Knowledge Foundry capture creates proposed notes only; knowledge promotion is separate from task promotion and never creates tasks/goals automatically.
- Idea Foundry promotion records decision evidence only and never creates tasks/goals automatically; explicit `idea create-goal` and `idea create-task` commands require that prior promotion evidence and create linked Dev-Flow state only.
- Goal lifecycle state is canonical under `.devflow/goals/<goal_id>/goal-state.yaml`. `goal activate/pause/block/complete/archive` write lifecycle evidence and hash-chained goal events only; freshness loop recommendations and explicit batch commands remain separate from providers, routing, promotion, commits, pushes, pull requests, and automatic goal completion.

## Sandbox & Security Boundaries

Destructive command filtering is intentionally shallow (detecting obvious fragments like `rm -rf /`, `mkfs`, `dd if=`). The Dev-Flow shell worker operates with trusted local credentials in the task workspace; it is path-isolated, not sandboxed.

The current safety model is trusted local single-user execution:

- shell and verification commands run as subprocesses in `.devflow/workspaces/<task-id>/`
- worker environment variables are filtered to an allowlist plus explicit task environment
- POSIX subprocesses are started in their own session so timeout and log-limit cleanup can terminate child processes in the same process group
- canonical task artifacts are written with same-directory temporary files followed by atomic replacement

This does not stop a command from using the local user's filesystem permissions, network access, CPU, memory, or other OS capabilities before Dev-Flow terminates it. It is not suitable for untrusted worker code, hostile repositories, shared multi-user hosts, or tenant isolation.

Current MVP implementation limits:

- default workspaces are copy-based scratchpads
- opt-in `--git-worktree` tasks create branch-backed worktrees and promote with Git-aware merge mechanics
- scheduler status is read-only derived state; `scheduler retry` writes only explicit retry-request evidence and does not change canonical task status or run workers
- copy-workspace promotion copies verified workspace changes into the main checkout instead of performing a git-native three-way merge
- patch application supports validated text patches only, requires matching fresh acceptable review and dry-run evidence, records SHA-256 patch evidence, and rejects binary diffs, renames, copies, mode changes, and similarity metadata
- event logs are append-only evidence, but task and system event writes are still separate writes and may require human-reviewed reconciliation after a crash

Future production hardening items:
- Multi-worker Git worktree attempts per task beyond the initial shell worker lane.
- Richer Git-native conflict handling and resolver-task UX.
- Multi-worker branch-sharing cleanup beyond the initial shell worker lane.
- Per-task temporary `HOME` and temp directories.
- Network-off runner policies.
- Ollama keep-alive and model-stop controls for local resource pressure.
- Resource limits for CPU, memory, file descriptors, and process counts.
- Allowlisted command profiles and absolute path inspections.
- Container, firejail, macOS sandbox, or other OS-level isolation.
- Cautious `devflow repair --dry-run` design after read-only reconciliation reporting stays stable.

## Out Of The Current Contract

- Browser or web dashboards.
- Token-context helper as runtime authority. The helper may exist as visible planning guidance, but it does not execute token tools, route models, install hooks, or change shell-worker, verification, or promotion behavior.
- Task-fit/context routing runtime beyond the Milestone 17 evidence-only commands.
- Provider-backed worker adapters. The stable non-shell model paths are limited to local `ollama run` evidence capture through `devflow task local`, explicit local patch proposal evidence through approved `ollama_chat` patch agents, and read-only local WorkerEvidence profiles. They do not use remote provider APIs, own canonical task state, verify, promote, or apply model output without explicit patch gates.
- Provider-backed Git worktree orchestration beyond the opt-in shell-worker lane.
- SQLite or any other database.
- Vector databases, RAG, ML training, hidden memory, or automatic self-training.
- Automatic merge, automatic copy-back, commit, push, or PR automation.
- Legacy task-packet and unified-diff workflow rituals.

> [!IMPORTANT]
> **Current Priority**: Operating Layer State Reconciliation & Operator Readiness. Milestone 14 goal execution control loop through Milestone 22 Question & Blocker Resume Loop are complete in the local main checkout. Dev-Flow is model-agnostic at the registry/role-selection boundary: local discovery, selected-agent evidence, and derived routing evidence rank or reject eligible installed profiles for explicit roles. Autonomous best-model-for-any-task routing remains excluded and does not enable remote provider execution, autonomous routing, auto-resume, auto-promotion, auto-commit, auto-push, pull requests, databases, worker-owned verification, or worker-owned promotion.
