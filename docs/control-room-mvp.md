# Dev-Flow Control-Room MVP

Date: 2026-05-27
Status: Active source of truth

## Product Compass

The long-term product North Star lives at [PRODUCT_NORTH_STAR.md](../PRODUCT_NORTH_STAR.md). Read it before implementation decisions and check proposed changes against its Periodic Self-Check section.

This document is the near-term MVP authority: it narrows the North Star into the first production-worthy control-room slice. The current command, filesystem, and safety contract lives at [docs/mvp-contract.md](mvp-contract.md).

For details on the project's design and boundaries:
- [docs/devflow-operating-model.md](devflow-operating-model.md) defines the role split between human, main chat/control-room agent, Dev-Flow kernel, worker agents, and DevMode.
- [docs/read-only-control-room-agent.md](read-only-control-room-agent.md) defines the main chat agent as read-only planner/spec/reviewer/coordinator.
- [docs/devmode-devflow-boundary.md](devmode-devflow-boundary.md) defines the boundary between DevMode discipline and Dev-Flow orchestration.
- [docs/architecture/agent-registry-and-adapter-runtime.md](architecture/agent-registry-and-adapter-runtime.md) defines the next provider/agent/role registry and adapter-runtime direction. [docs/architecture/agent-selection-and-context-routing.md](architecture/agent-selection-and-context-routing.md) defines the later task-fit, context-estimation, capability-profile, context-pack, scout, and routing feedback design. Both are design-only until implementation work explicitly promotes a slice.
- [docs/architecture/git-native-worker-isolation-and-promotion.md](architecture/git-native-worker-isolation-and-promotion.md) defines the opt-in Git-backed worker branches/worktrees, commit-bound verification, Git-native promotion preview, and human-controlled promotion slice.
- [docs/architecture/patch-application-and-readiness-gating.md](architecture/patch-application-and-readiness-gating.md) defines the explicit patch application gating and verification/readiness invalidation gating (Milestones 9 & 10).
- [docs/architecture/multi-project-registry.md](architecture/multi-project-registry.md) defines the first-class multi-project registry, project creation/import commands, and local-first Git/GitHub publication policy.
- [docs/architecture/project-task-lifecycle-contract.md](architecture/project-task-lifecycle-contract.md) defines project-local state authority, task ownership, registry/index boundaries, and nested-directory path resolution.
- [docs/architecture/goal-control-loop.md](architecture/goal-control-loop.md) defines the PLC-style goal control loop direction: every iteration checks Git checkpoint/push opportunities first, then reconciles project-local goals, task slices, parallel lanes, verification evidence, and blockers.


## Product Direction

Dev-Flow is being rebuilt as a local-first control room for parallel AI coding workers.

The product is not a coding agent, model provider, memory framework, IDE workflow, or software-factory ritual. Dev-Flow owns the boring but sacred control-plane pieces around replaceable workers:

- task state
- isolated workspaces
- locks and ownership
- worker process lifecycle
- status and logs
- result bundles
- verification evidence
- merge readiness

Workers can be shell commands today and Aider, Hermes, OpenCode, Codex, Claude Code, local models, manual packets, or future tools later. The current runtime intentionally implements shell workers only. Future worker types must be introduced through the registry and adapter-runtime sequence, not wired directly into task execution.

## Non-Negotiable Principles

1. Agents are replaceable. State is sacred.
2. One task gets one isolated workspace and one owner.
3. Visibility is required through plain filesystem artifacts and CLI output before broader UI surfaces.
4. Context is durable artifacts, not hidden magic memory.
5. Autonomy is earned by reliable status, logs, recovery, and reviewable results.

## Current Control-Room Contract

The current stable milestone is the shell-worker control-room path plus one manual proof-agent contract, one legacy local Ollama advisory wrapper, the registry-backed Qwopus patch-proposal path, a practical registry-backed local model worker-pool evidence slice, a passive review-readiness scorecard, local Idea Foundry intake evidence, and the explicit idea-to-execution bridge. It includes task lifecycle commands, init/doctor structure checks, text-only terminal dashboard visibility, verification evidence, review-readiness status, TaskPacket projection, logs, human-controlled promotion from isolated workspaces, a bounded handoff for `devflow-manual-codex-worker`, local Qwen/Qwopus/Gemma prompt/response capture that does not edit code, canonical local `proposal.patch` evidence from `task run --worker qwopus-implementer`, generalized WorkerEvidence from read-only local model profiles, human-reviewed idea capture/classification/promotion decisions, and explicit `idea create-goal` / `idea create-task` commands that require prior promotion evidence.

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
devflow task review-patch <task_id>
devflow task review-patch <task_id> --project factory-scheduler
devflow task review-patch <task_id> --agent qwopus-implementer
devflow task patch-dry-run <task_id>
devflow task patch-dry-run <task_id> --project factory-scheduler
devflow task patch-dry-run <task_id> --agent qwopus-implementer
devflow task apply-patch <task_id> --agent qwopus-implementer
devflow task apply-patch <task_id> --project factory-scheduler --agent qwopus-implementer
devflow task apply-patch <task_id> --run-id <run_id>
devflow task verify <task_id> --shell "test -f result.txt"
devflow task verify <task_id> --project factory-scheduler --shell "test -f result.txt"
devflow task local <task_id> --agent qwen-planner
devflow task local <task_id> --agent qwopus-implementer
devflow task local <task_id> --agent gemma-reviewer --input-worker qwopus-implementer
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
devflow idea promote <idea_id> --to goal --rationale "human reviewed"
devflow idea create-goal <idea_id> --dry-run
devflow idea create-goal <idea_id>
devflow idea create-task <idea_id> --dry-run
devflow idea create-task <idea_id>
devflow idea archive <idea_id> --reason "superseded"
devflow dogfood list
devflow dogfood show <case_id>
devflow dogfood run --suite production-readiness
devflow dogfood score <run_id>
devflow dogfood report <run_id>
devflow release readiness --pytest-evidence <pytest-log> --stale-context-evidence <stale-context-log>
devflow agent show devflow-manual-codex-worker
devflow agent list --json
devflow agent show local-qwopus-inspector --json
devflow agent policy --json
devflow agent run --task <task_id> --profile local-qwopus-inspector --dry-run --json
devflow agent packet <task_id> devflow-manual-codex-worker
devflow task run <task_id> --worker devflow-manual-codex-worker
```

The preferred shell-worker form is `devflow task run <task_id> --worker shell -- <command>`. The `--shell "<command>"` form remains supported.

The project-management form is `devflow project create "Name"`. It creates a separate local project root under the configured projects root, initializes local Git by default, creates that project's own `.devflow/` scaffold, and registers the project in `~/.devflow/registry/projects.json`. It does not create a GitHub repository, add a remote, push, publish, or create a hidden initial commit by default. For local-Git managed projects, create an explicit local baseline from the project root with `devflow git checkpoint --message "chore: initialize project baseline" --yes` before creating project-scoped tasks; `task create --project` refuses unborn managed Git projects so copied workspaces and promotion previews have a real baseline commit. Existing project roots can be registered with `devflow project import /path/to/project`. `devflow dashboard --all-projects` renders the registry as a multi-project control-room view while preserving the existing single-project dashboard behavior.

A missing registered project path is handled as explicit human-decision registry hygiene. The first command is `devflow project doctor <project_id>`. If the project exists elsewhere, the human repairs the registry by importing or re-registering the real project root. If the project was temporary, deleted, or intentionally retired, the default cleanup is `devflow project archive <project_id>` so the record remains audit-visible through `project list --include-archived` but drops out of normal lists and all-project scans. `devflow project remove <project_id> --registry-only` is reserved for junk registry entries that should not remain in audit history. Read-only all-project surfaces report missing paths and recommend `project doctor`; they do not recreate, archive, remove, publish, push, or call providers.

Project task state is project-local. Without `--project`, task commands resolve the nearest ancestor that owns a `.devflow/` directory, falling back to the current directory only when no project-local state exists. With `--project <project_id>`, task create/list/show/run/verify/packet/review/next-action/log/review-patch/patch-dry-run/apply-patch/promote-preview/promote resolve the project root from `~/.devflow/registry/projects.json` and read or write that project's `.devflow/tasks/` and `.devflow/workspaces/` as appropriate. Task IDs remain unique within each project, not globally; cross-project output displays task refs as `<project_id>:<task_id>`. Project-scoped `promote-preview` is read-only. Project-scoped `promote` preserves the existing human confirmation and promotion safety gates while applying changes to the registered project root, not the caller's current directory.

When `--project` is omitted, task commands walk upward from the current directory to the nearest ancestor containing `.devflow/`. This keeps project-local state authoritative when commands are run from nested subdirectories and avoids accidental nested `.devflow/` split-brain state. If no ancestor contains `.devflow/`, bootstrap-compatible commands use the current directory.

The proof-agent form is `devflow task run <task_id> --worker devflow-manual-codex-worker`. It creates a Codex-ready manual handoff and bounded packet for a human-launched worker. The worker may edit only `.devflow/workspaces/<task_id>/` and may write evidence only under `.devflow/tasks/<task_id>/agents/devflow-manual-codex-worker/`. Dev-Flow remains responsible for verification, merge readiness, and human-controlled promotion.

The Project Code Map form is `CODE_MAP.md` plus `devflow map init`, `devflow map show`, and `devflow map check`. The map is a human-authored orientation artifact. When present, `devflow task packet <task_id>` includes a bounded excerpt so workers can orient before broad repo scans. The map is read-only context, not canonical task state, and it does not route models, call providers, or generate itself from source.

The registry-backed local Qwopus form is `devflow task run <task_id> --worker qwopus-implementer`. It calls local Ollama, writes `proposal.patch`, `raw_output.md`, `result.md`, `run.json`, and `logs/worker.log` under `.devflow/tasks/<task_id>/agents/qwopus-implementer/`, and stops. Dev-Flow remains responsible for explicit patch review, dry-run preview, application to the isolated workspace, verification, merge readiness, and human-controlled promotion. The `review-patch --agent` and `patch-dry-run --agent` forms normalize agent patch evidence into `.devflow/tasks/<task_id>/local-model-runs/<run_id>/`; apply-patch refuses mutation unless matching fresh acceptable review and dry-run evidence exists in the resolved project root. Normalized local-model patch review and patch dry-run evidence are documented in [docs/architecture/patch-evidence-ladder.md](architecture/patch-evidence-ladder.md); dry-run preview is evidence only and does not mutate source or workspace files.

The orchestration policy form is `devflow task orchestrate <task_id> --plan-only`. It writes task-local policy evidence with Git/DevMode baseline, allowed roles, context layers, write boundaries, stop conditions, and human promotion requirements. It does not execute workers, call provider APIs, route autonomously, apply patches, verify, promote, or mutate main.

The guardrail outcome metadata form is `devflow worker validate-outcome <path-to-outcome-json>`. It validates worker outcome metadata and writes validation evidence only. It does not run agents, apply patches, verify code, promote, route models, or mutate `task.yaml`.

The freshness loop form is `devflow freshness loop`. It runs one control-loop iteration against canonical goal and task state, writes a derived snapshot to `.devflow/freshness/latest.json`, appends `.devflow/freshness/events.jsonl`, updates each goal's derived `.devflow/goals/<goal_id>/loop-state.json`, records the loop-start Git checkpoint/push decision, projects per-goal loop state plus parallel-safe task lane recommendations, groups ready lanes into conflict-aware parallel batches using declared `shared_files`, projects conflict-aware shell-worker batches from concrete slice `worker_policy` command lists, projects conflict-aware verification batches from concrete slice `verification_policy` command lists, and reports stale or contradictory goal/task/handoff guidance. `devflow freshness run --max-iterations N` repeats that PLC-style loop within a strict iteration bound, persists a derived run report under `.devflow/freshness/control-runs/`, stops when state is stable, and stops before dispatch when Git checkpoint/push/sync/repair or human decisions are required. `devflow freshness run --all-projects --max-iterations N` repeats bounded-parallel, read-mostly scans across registered project roots, writes an aggregate bounded run report under `~/.devflow/freshness/control-runs/`, and refuses dispatch flags because project-level integration remains a controlled lane. `devflow freshness create-batch <goal_id> <batch_id>` creates tasks for one currently projected conflict-safe parallel batch, using the existing goal slice task-creation path and serializing canonical state writes. `devflow freshness run --create-tasks` is the explicit task-creation dispatch mode: it may create the first currently projected parallel task batch in a safe iteration, then loops again so the resulting checkpoint opportunity is surfaced before more work. `devflow freshness worker-batch <goal_id> <batch_id> --max-parallel N` executes one currently projected safe shell-worker batch with task-grained parallel subprocesses while preserving existing `run_shell_task` locks, logs, task events, and workspaces. `devflow freshness run --execute-workers` is the explicit worker dispatch mode: it may run the first currently projected shell-worker batch in a safe iteration, then loops again so changed workspace/task evidence is observed and the next Git checkpoint opportunity is surfaced before more work. `devflow freshness run --execute-verification` is the explicit verification dispatch mode: it may run the first currently projected verification batch in a safe iteration, then loops again so the next Git checkpoint opportunity is surfaced before more work. `devflow freshness verify-batch <goal_id> <batch_id> --max-parallel N` executes one currently projected safe verification batch with task-grained parallel subprocesses while preserving the existing `verify_task` locks, logs, `verification.json`, and task events. Batch creation, worker runs, and verification write derived reports under `.devflow/freshness/task-batch-runs/`, `.devflow/freshness/worker-runs/`, `.devflow/freshness/verification-runs/`, and `.devflow/freshness/control-runs/`; those reports are evidence about bounded control activity, never goal-completion certificates. The single-iteration CLI loop still projects only. `devflow freshness loop --all-projects` runs that same project-local loop across registered project roots with bounded concurrency, writes each project's local freshness snapshot, reassembles aggregate output in registry order, and writes a registry-level snapshot to `~/.devflow/freshness/latest-all-projects.json`. Missing active project paths are reported as human-decision items pointing to `devflow project doctor <project_id>` instead of crashing the loop. When repair is ambiguous, the loop exits with a human-decision status instead of rewriting docs, canonical goal artifacts, registry entries, commits, remotes, spawning workers, or starting verification processes.

Knowledge Foundry commands write proposed/promoted/rejected reusable notes under `.devflow/knowledge/`. Knowledge promotion is separate from task promotion; capture never silently converts ideas into tasks or goals. This is local human-reviewed curation, not ML training, hidden agent memory, vector search, or RAG.

The Idea Foundry form is `devflow idea capture/list/show/classify/promote/create-goal/create-task/archive`. It stores project-local intake evidence under `.devflow/ideas/<idea_id>/`, keeps raw ideas separate from goals and tasks until explicit bridge creation, and records human classification and promotion decisions. `devflow idea create-goal` and `devflow idea create-task` require prior matching human promotion evidence, write bidirectional idea-to-goal/task links, and create Dev-Flow state only. Idea creation commands do not run workers, call providers, verify, promote code, commit, push, open pull requests, or route models.

The dogfood production-readiness form is `devflow dogfood run --suite production-readiness`. It runs deterministic local cases against existing Dev-Flow control-room surfaces and writes scorecards under `.devflow/dogfood/`. It measures safety, pipeline correctness, context efficiency, worker artifact quality, recovery handling, knowledge capture, operating-layer visual QA, and lightweight behavior. The visual QA case requires desktop/mobile current and baseline artifacts for `devflow operating-layer visual-qa`, accepts deterministic fallback PNG/SVG evidence as the minimum, upgrades to external/Appshot PNGs when present, and uses optional Playwright browser rasters when available. Dogfood closes any task records it creates with the `evidence-only` outcome after each case so test evidence does not remain in the active project queue. It is not autonomous model execution: it does not call providers, route workers, promote, push, create a database, create a dashboard, run a daemon, use vector search/RAG/embeddings, or train models.

The release-readiness form is `devflow release readiness --pytest-evidence <pytest-log> --stale-context-evidence <stale-context-log>`. It is a read-only milestone gate over explicit evidence: clean Dev-Flow Git status, captured full-suite pytest output, latest production-readiness dogfood Silver-or-better scorecard, operating-layer visual QA desktop/mobile evidence, stale-context scan evidence, and a standard handoff report with one next safe action. It does not run heavy suites, mutate task state, promote, push, tag, build, or publish; it makes the release gate explicit after the expensive verification commands have already been run and captured.

The local operating-layer form is `devflow operating-layer snapshot --json` and `devflow operating-layer serve --host 127.0.0.1 --port 8765`. It is the approved UI contract for a browser-friendly control-room surface. It composes existing project, goal, task, freshness, verification, evidence, question, lane, and promotion projections into one derived snapshot and serves a local static UI over that same snapshot. The Action Rail may execute supervisor-classified read-only Dev-Flow commands through the local server. The approval-gated browser mutation path is limited to exact task verification and exact task promotion commands after explicit human approval; the server rechecks the supervisor classifier, refuses placeholder verification commands, and preserves the existing promotion safety gates. Worker execution, task creation/patch application, git publication, and other approval-required commands remain blocked for trusted CLI execution. The filesystem remains the source of truth; the snapshot is derived and disposable. See [docs/architecture/local-operating-layer-ui.md](architecture/local-operating-layer-ui.md).

The legacy local Ollama advisory form is `devflow task local <task_id> --agent qwen-planner`, `devflow task local <task_id> --agent qwopus-implementer`, or `devflow task local <task_id> --agent gemma-reviewer --input-worker qwopus-implementer`. It runs `ollama run <model>` through a local subprocess, writes prompt/response/run metadata under `.devflow/workspaces/<task_id>/local-workers/<worker-name>/`, and updates `task.yaml` plus hash-chained events. It does not write `proposal.patch`, auto-edit repo files, parse model output as truth, route autonomously, verify, commit, merge, promote, or call remote provider APIs.

The registry-backed local model worker-pool form is `devflow agent run --task <task_id> --profile local-qwopus-inspector --dry-run --json` for preview and `devflow agent run --task <task_id> --profile local-qwopus-inspector --json` for the first real vertical slice. It treats Josh's local fleet as heterogeneous: Mac mini runs small utility/helper workers, Mac Studio runs heavy reasoning/implementation/review workers, and `qwen2.5-coder:14b` is configurable as `either`. Profiles include machine class, weight class, model role name, caution notes, manifest verification command, and alias metadata. The real slice builds a bounded TaskPacket, calls `local_model_client.py`, writes WorkerEvidence under `.devflow/tasks/<task_id>/local-model-runs/<run-id>/`, caps raw output, captures failure, and stops. Gemma summarizer profiles use a compact evidence packet plus native Ollama `/api/chat` with thinking disabled when required by the model/template. It does not edit source files, write `proposal.patch`, apply patches, verify, commit, merge, push, promote, or mutate canonical task state. See [docs/architecture/local-model-worker-pool.md](architecture/local-model-worker-pool.md).

Do not implement these in the first milestone:

- Aider
- Hermes worker/runtime adapter (external operator gateway docs are allowed)
- OpenCode
- memory
- complex scheduling
- autonomous routing
- remote provider-backed adapter calls before explicit promotion into the runtime contract
- old task-packet workflow orchestration
- PR automation
- autonomous browser/web dashboard mutation surfaces
- token-context routing helpers beyond the current read-only planning helper
- task-fit/context routing runtime
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

Closed-task cleanup and pruning are separate retention controls. `devflow task cleanup <task_id> --preview` and `--apply` remove only closed-task runtime artifacts under `.devflow/workspaces/<task_id>` or `.devflow/worktrees/<task_id>/<worker>`, while retaining `.devflow/tasks/<task_id>/` evidence. `devflow task prune-closed --preview --older-than <duration>` reports old closed-task evidence directories eligible for deletion and writes `.devflow/prune-runs/<run-id>.json`; `--apply` deletes only safe, eligible `.devflow/tasks/<task_id>/` evidence after repeating the same checks. It refuses active tasks, missing closure metadata, symlinked/path-traversal evidence paths, and anything outside `.devflow/tasks/`.

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

## Acceptance Gauntlet

Create one shell task, run `echo hello > result.txt`, verify `test -f result.txt`, list it, show it, inspect the dashboard, preview promotion, and promote only after explicit human approval. Before promotion, the command result must exist only under `.devflow/workspaces/<task_id>/`. No worker may mutate the main checkout directly. No provider-backed adapters, database, autonomous browser dashboard mutation surface, or worktree orchestration are part of this acceptance test. The manual proof-agent acceptance path additionally requires `agent show`, `agent packet`, and `task run --worker devflow-manual-codex-worker` to produce bounded handoff/evidence surfaces without executing provider APIs.

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
- local operating-layer snapshot and supervisor-safe Action Rail controls for browser-friendly UI state
- read-only crash/interruption reconciliation reporting for partial event writes, task/system event divergence, interrupted promotion evidence, and inconsistent task artifacts
- stable `devflow-manual-codex-worker` registry contract
- proof-agent bounded packets with role, allowed reads, allowed writes, forbidden writes, required outputs, completion rules, and manual instructions
- manual proof-agent handoff generation without provider API calls, model selection, routing, scheduling, auto-verification, or auto-promotion
- task show/dashboard visibility for manual proof-agent complete, blocked-question, and failure evidence
- adapter maturity boundary with only `shell` and `manual` classified as executable `stable_runtime` adapters
- clear task-run refusal for `experimental_readonly` and `planned_not_executable` adapters
- promotion preview from isolated workspace changes
- human-controlled promotion of verified changes to the main checkout
- task closure evidence with explicit outcomes, inactive closed status, and preserved logs/artifacts
- preview-first cleanup for closed tasks that removes only conservative task-owned `.devflow` runtime artifacts on `--apply`
- preview-first pruning for old closed-task evidence that deletes only safe `.devflow/tasks/<task_id>/` evidence on explicit `--apply` and records `.devflow/prune-runs/<run-id>.json`
- `devflow task local` for local Qwen/Qwopus/Gemma advisory evidence capture with 600-second defaults, raw response preservation, stderr capture, and run metadata under the task workspace
- `devflow task run --worker qwopus-implementer` for canonical local Ollama `proposal.patch` evidence that Dev-Flow applies and verifies separately
- `devflow task orchestrate --plan-only` for plan-only parallel-worker policy evidence
- `devflow worker validate-outcome` for structured guardrail outcome metadata validation
- Knowledge Foundry commands for proposed/promoted/rejected local reusable knowledge notes
- Idea Foundry commands for raw idea intake, human classification, decision-only promotion, explicit goal/task creation after prior promotion evidence, and archival evidence
- canonical goal lifecycle state under `.devflow/goals/<goal_id>/goal-state.yaml`, with explicit `goal activate/pause/block/complete/archive` commands, lifecycle-aware goal status/next output, freshness dispatch gating for paused/blocked/complete/archived goals, operating-layer lifecycle display, and human-controlled closure recommendations after promoted task-slice evidence

Outside the current product contract:

- autonomous browser/web dashboard mutation surface
- token-context helper (Completed helper; acts purely as a visible planning helper that recommends context strategy. It does not execute token tools, route models, install hooks, or change shell-worker, merge, or verification behavior.)
- task-fit/context routing (Design documented only. It does not select agents, invoke scouts, build runtime context packs, or change shell-worker behavior.)
- provider-backed non-shell worker adapters
- Ollama keep-alive/model-stop controls for local resource pressure
- agent registry and adapter-runtime implementation beyond the stable proof-agent contract
- SQLite or other databases
- provider-backed `.devflow/worktrees/` orchestration beyond the opt-in shell-worker slice
- multi-worker worktree scheduling, branch-sharing cleanup beyond strict doctor detection, and provider-backed Git worktree promotion beyond the current opt-in shell-worker slice
- vector databases, RAG, ML training, hidden memory, and automatic self-training

> [!IMPORTANT]
> **Current Priority**: Milestone 14 goal execution control loop is implemented and Milestone 14A hardening is complete. The next planned slice is multi-project control room hardening. Goal lifecycle and freshness execution commands do not call providers, route models, auto-promote, auto-commit, auto-push, open pull requests, or mark goals complete without explicit human command evidence.


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
* **Dashboard / Web Server**: No database-driven dashboard (text-only terminal dashboard remains static).
* **Databases**: Relies strictly on plain filesystem architecture; no SQL/NoSQL databases.
* **Automated Merging**: No automatic pull request creation or branch merging.

### Dogfooding Requirement

Future implementation slices should use Dev-Flow shell tasks or local worker commands where practical. This is required dogfooding for task isolation, logs, verification evidence, dashboard visibility, promotion previews, and handoff quality. It must not be used as justification to add provider-backed adapters, autonomous routing, scheduling, or old workflow machinery before the shell-worker and manual proof-agent loop stays stable.

Run `devflow dogfood run --suite production-readiness` as the lightweight milestone readiness harness when changing the control-room pipeline. Silver is the current local readiness gate; lower scores should drive the smallest real improvement rather than weaker cases. Operating-layer changes must preserve the visual QA case, including desktop/mobile evidence, no-overflow checks, Orchestrator-first ordering, worker progress rows, Action Rail safety state, and current/baseline status.

Before tagging, building, or calling a milestone ship-ready, run `devflow release readiness --pytest-evidence <pytest-log> --stale-context-evidence <stale-context-log>` against a clean checkpoint after full pytest, production-readiness dogfood, operating-layer visual QA, and stale-context search evidence have been captured.

---

### Next Phase Outlook

Future adapter development may only begin using this stable checkpoint and [docs/architecture/agent-registry-and-adapter-runtime.md](architecture/agent-registry-and-adapter-runtime.md) as boundaries. The next phase must strictly preserve:
1. **Local-First State**: Rely on plain-file source of truth before any database storage.
2. **Workspace Isolation**: Ensure replaceable workers operate strictly within copied sandboxes.
3. **Verification Ownership**: Control-plane holds authoritative ownership of verification execution.
4. **Human-Controlled Promotion**: Keep humans at the helm of promotion and merge-readiness approvals.
