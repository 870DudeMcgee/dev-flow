# Hermes Operator Layer

Hermes Agent OS is an external operator, chat, scheduling, and delegation layer over Dev-Flow. Hermes may operate Dev-Flow through supervisor-safe commands. Hermes may not become Dev-Flow.

Dev-Flow remains the durable engineering control room and source of truth for:

- task state
- task evidence
- worker isolation
- verification records
- git readiness
- cleanup previews and apply gates
- promotion readiness and promotion

Codex, Qwopus, shell, Antigravity, and other local workers are replaceable execution engines. Josh remains the promotion authority. Hermes memory is convenience context only; Dev-Flow artifacts beat Hermes memory every time.

## Operator Flow

```text
Josh / iPhone / Mac / Hermes CLI / iMessage / gateway
  -> Hermes Agent OS
  -> Dev-Flow supervisor-safe commands
  -> Dev-Flow filesystem/task/evidence state
  -> workers such as Codex, Qwopus, shell, Antigravity
  -> Dev-Flow verification/review/promotion
  -> Josh approves promotion
```

Hermes should prefer JSON surfaces:

```bash
PYTHONPATH=src .venv/bin/python -m devflow.cli status --json
PYTHONPATH=src .venv/bin/python -m devflow.cli dashboard --json
PYTHONPATH=src .venv/bin/python -m devflow.cli supervisor policy --json
PYTHONPATH=src .venv/bin/python -m devflow.cli supervisor packet --json
PYTHONPATH=src .venv/bin/python -m devflow.cli supervisor route-message "raw Telegram text" --json
PYTHONPATH=src .venv/bin/python -m devflow.cli hermes imessage-check --json
PYTHONPATH=src .venv/bin/python -m devflow.cli task next-action <task-id> --json
PYTHONPATH=src .venv/bin/python -m devflow.cli task review <task-id> --json
PYTHONPATH=src .venv/bin/python -m devflow.cli agent list --json
PYTHONPATH=src .venv/bin/python -m devflow.cli agent policy --json
PYTHONPATH=src .venv/bin/python -m devflow.cli agent run --task <task-id> --profile local-qwopus-inspector --dry-run --json
```

## Operating Rules

Hermes defaults to read-only. It may inspect, summarize, recommend next safe actions, prepare Codex prompts, notify a human operator, run scheduled read-only briefs, and capture approved ideas through Dev-Flow commands.

The Mac mini local-model setup and Telegram rollout sequence lives in [hermes-telegram-mac-mini-rollout.md](hermes-telegram-mac-mini-rollout.md). Use that document as the active setup goal before enabling Telegram-triggered read-only auto-runs.

Telegram is a lightweight command surface, not a second brain. Hermes may receive Telegram text and ask Dev-Flow to classify it with `devflow supervisor route-message`. Dev-Flow owns the routing policy and exposes the Telegram default as local `gemma4:latest` through `devflow supervisor policy --json`. Dev-Flow returns the route, selected local model when applicable, action, reason, safety metadata, and a tiny footer. Hermes should append or preserve that footer in responses so real use can tune the policy:

```text
route: devflow_read
model: gemma4:latest
action: run_safe_command
```

Hermes should follow `operator_plan.next_step`:

- `run_recommended_command`: run `recommended_command` only when `operator_plan.may_auto_run_command` is true, summarize the command output briefly, then append `operator_plan.routing_footer`.
- `answer_with_model`: answer with `operator_plan.model`, keeping the response short for Telegram, then append the footer.
- `request_human_approval`: do not run the command or create work yet. If Dev-Flow returns `operator_plan.pending_action`, store that exact action for the Telegram session, ask for explicit approval using `operator_plan.approval_prompt_hint`, then execute the stored action exactly once after `/approve`.

Hermes must not invent a mutation command from the chat text. Only Dev-Flow may produce `operator_plan.pending_action`, and Hermes may execute only that exact pending action after approval.

Hermes must not directly edit:

- `.devflow/`
- source files
- the git index
- branches
- remotes
- promotion state

Human approval remains required for project creation/import/archive/remove, task creation, knowledge capture, worker execution, verification runs, cleanup apply, patch application, promotion, merge, push, and broad mutation. Hermes may recommend those actions only after citing Dev-Flow readiness evidence and the exact command for the human to approve.

## Gateway And Mobile Use Cases

Good Hermes use cases:

- answer "what is happening?" from chat or mobile
- summarize review queue and blocked tasks
- prepare short Codex prompts grounded in task evidence
- remind Josh about stale or failed work
- ask for explicit approval before a bounded mutation
- report the next safe action without dumping raw logs

Bad Hermes use cases:

- hidden background schedulers that mutate Dev-Flow
- auto-promotion or auto-push
- using Hermes memory as canonical project state
- direct source edits outside a task workspace/worktree
- unbounded worker spawning
- mixing personal/iMessage automation authority with repo authority

## Scheduled Briefs

Hermes cron jobs are allowed only as bounded status/reporting loops unless Josh explicitly approves a separate mutation command. When remote advisory is explicitly enabled for a cron profile, the allowed provider call is one default Flash advisory run:

```bash
devflow agent advise --profile deepseek-v4-flash-planner --job gap-analysis --json
```

The cron heartbeat should gather bounded evidence first: `devflow status --json`, `devflow supervisor packet --json`, `devflow git status`, the latest verification-ledger summary, and targeted stale-context search results. The advisory run may write recommendation evidence under `.devflow/reports/agent-advisory-runs/<run_id>/`, including an exact suggested `devflow task create ...` command, but Hermes must not execute that suggestion. Pro advisory runs require explicit job/profile selection, not automatic escalation. `devflow agent propose-patch` is human-direct patch evidence only; it is not Hermes-delegable and must never be run from unattended Hermes automation.

### Morning Dev-Flow Brief

- Read-only commands: `status --json`, `supervisor packet --json`, `git status`
- Output: status, review queue, blocked tasks, one next safe action
- Alert-worthy: failed verification, dirty main checkout, stale/conflicted promotion evidence
- Must not: run workers, verify, cleanup, promote, push, or create tasks

### Evening Dev-Flow Debrief

- Read-only commands: `dashboard --json`, `task list`, `supervisor packet --json`
- Output: what changed today, what remains active, what needs Josh
- Alert-worthy: long-running active tasks, failed runs, missing evidence
- Must not: close tasks or promote work automatically

### Stale Task Watchdog

- Read-only commands: `status --json`, `task next-action <task-id> --json`
- Output: stale/blocked list and recommended human-safe next action
- Alert-worthy: stale/conflicted promotion evidence, failed verification, old active tasks
- Must not: repair state, remove locks, or delete worktrees

### Git Hygiene Check

- Read-only commands: `git status`, `worktree list`, `branch list`
- Output: main cleanliness, Dev-Flow worktrees, Dev-Flow branches
- Alert-worthy: dirty main checkout, orphaned worktree candidates, diverged main
- Must not: run `git checkpoint --message "<message>" --yes`, `sync-main`, `push-main`, `worktree prune --apply`, or `branch archive` without explicit approval

### Knowledge/Idea Review Queue

- Read-only commands: `knowledge list`, `knowledge search <query>`
- Output: proposed notes that need human review
- Alert-worthy: useful notes stuck in proposed state
- Must not: promote/reject knowledge or create tasks without approval

## Skill And Profile Boundaries

Hermes profiles that can read personal messages or mobile gateways must not inherit mutation authority over Dev-Flow. Keep a dedicated Dev-Flow operator profile with:

- read-only default
- command allowlist
- no secrets in logs
- short status replies for iMessage
- explicit approval language before mutation
- Dev-Flow artifacts as canonical state

## Path Authority

Portable checkout authority:

```text
<repo-root>
```

The old local checkout path is quarantined and must not be used for current work:

```text
/Users/jewelbait/Desktop/DevFlow
```

Use `<repo-root>` for portable command examples. This checkout is referred to as `DevFlow` in docs and handoffs, but operators should use their actual repo root. Do not restore legacy/quarantined material into active authority.

---

## Model Routing Configuration

The Hermes `~/.hermes/config.yaml` has a `model_routing` section that routes tasks to the best model based on keyword patterns. The current setup has six tiers with fallback chains:

| Tier | Primary Model | Fallbacks | Triggers |
|---|---|---|---|
| 1 Heavy | DeepSeek V4 Pro (paid) | V4 Flash paid → V4 Flash free → Qwopus local | refactor, debug, architect, security audit |
| 2 Code | DeepSeek V4 Flash:free | V4 Flash paid → Qwopus devflow local | code, write, implement, function, class |
| 3 Vision | Qwopus 32B local → Gemma 4 31B local | (local only — DeepSeek has no vision) | screenshot, ui, visual, image, mockup |
| 4 Simple | Qwen Coder 7B local | V4 Flash:free | typo, rename, docstring, trivial |
| 5 Planning | Qwen 3.6 128k local | V4 Flash free → V4 Flash paid | plan, synthesize, architecture, roadmap |
| 6 Review | Gemma 4 31B review local | V4 Flash free → V4 Flash paid | review, audit, code review, PR |

### Fallback behavior

Each tier's `fallback_models` chain activates when:
- The primary model is rate-limited (free tier exhausted)
- The primary provider is unreachable
- The model lacks required capabilities (e.g., DeepSeek has no vision)

### Mid-session model switching

Use Hermes slash commands to switch models without restarting:

```
/model               # Interactive model picker
/model deepseek/deepseek-v4-flash         # Switch to paid Flash
/model deepseek/deepseek-v4-flash:free    # Switch to free Flash
/model qwopus-32b:latest                  # Switch to local Qwopus
/model gemma4-31b:latest                  # Switch to local Gemma 31B
```

For vision tasks that fail because the chat model lacks vision:
1. Attach the image with `/image /path/to/screenshot.png`
2. Switch to a vision-capable model: `/model qwopus-32b:latest`
3. Ask the question

Or use the `vision_analyze` tool directly — it auto-routes to `google/gemini-2.5-flash` via the auxiliary vision config, regardless of the chat model.

### Adding multiple OpenRouter keys for rate-limit rotation

Credential pooling rotates across multiple API keys when one hits rate limits:

```bash
# Add a second OpenRouter API key to the pool
hermes auth add openrouter
# Follow the prompt to enter the second key
# Hermes auto-rotates on 429 responses
```

Verify with:
```bash
hermes auth list openrouter
```

### Verification

After config changes, restart the gateway:
```bash
hermes gateway restart
```

Then test routing:
```bash
hermes chat -q "Fix typo in docstring"        # → local-coder-fast
hermes chat -q "Review this pull request"      # → local reviewer
hermes chat -q "Design the auth architecture"  # → V4 Pro
hermes chat -q "Implement login function"      # → V4 Flash free
```

## Non-Goals

This integration does not add a Hermes worker adapter, provider-backed task-run execution, a dashboard server, a database, autonomous routing, hidden memory, or a competing orchestration loop. The OpenRouter/DeepSeek advisory lane is Dev-Flow-owned report evidence that Hermes may schedule only under the bounded cron rule above. Future non-shell worker runtime work must follow the registry and adapter sequence documented in the active architecture notes.
