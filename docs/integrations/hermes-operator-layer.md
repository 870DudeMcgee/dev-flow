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

Codex, Sonnet, Opus, Qwen, MiniMax, shell, and local models are replaceable execution engines. Josh remains the promotion authority. Hermes memory is convenience context only; Dev-Flow artifacts beat Hermes memory every time.

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
PYTHONPATH=src .venv/bin/python -m devflow.cli agent run --task <task-id> --profile hermes-gemma12b --dry-run --json
```

## Operating Rules

Hermes defaults to read-only. It may inspect, summarize, recommend next safe actions, prepare Codex prompts, notify a human operator, run scheduled read-only briefs, and capture approved ideas through Dev-Flow commands.

The Mac mini local-model setup and Telegram rollout sequence lives in [hermes-telegram-mac-mini-rollout.md](hermes-telegram-mac-mini-rollout.md). Use that document as the active setup goal before enabling Telegram-triggered read-only auto-runs.

Telegram is a lightweight command surface, not a second brain. Hermes may receive Telegram text and ask Dev-Flow to classify it with `devflow supervisor route-message`. Dev-Flow owns the routing policy and exposes the Telegram default as local Hermes provider `custom:hermes-qwen32` with model `qwen35-9b-mtp` through `devflow supervisor policy --json`. Dev-Flow returns the route, selected local model when applicable, action, reason, safety metadata, and a tiny footer. Hermes should append or preserve that footer in responses so real use can tune the policy:

```text
route: devflow_read
model: qwen35-9b-mtp
action: run_safe_command
```

Dev-Flow discovers the active Hermes config and local OpenAI-compatible model endpoints at runtime. Operators should inspect `devflow agent catalog --json` instead of copying machine-specific model maps between Macs. The catalog exposes machine RAM/classification, the default local model, configured/discovered Hermes providers, model fit, and the local concurrency rule. On current Mac mini setup, `qwen35-9b-mtp` is the preferred local default. Gemma is not the default local model.

## Profile Selection Guide

The selectable Dev-Flow model surface uses canonical Hermes profile IDs only. Retired `df*`, `dflocal*`, role-only, and bare local aliases may appear in cleanup reports for historical evidence, but they are not new picker or command identities.

| Use | Hermes profile | Provider | Model |
|---|---|---|---|
| Default coding worker | `hermes-codex-gpt55` | `openai-codex` | `gpt-5.5` |
| Alternative coding model | `hermes-minimaxm3` | `openrouter` | `minimax/minimax-m3` |
| Efficient Qwen plus | `hermes-qwen37plus` | `openrouter` | `qwen/qwen3.7-plus` |
| Strong Qwen max | `hermes-qwen37max` | `openrouter` | `qwen/qwen3.7-max` |
| Balanced paid coding/review | `hermes-sonnet46` | `openrouter` | `anthropic/claude-sonnet-4.6` |
| Deep architecture/judging | `hermes-opus48` | `openrouter` | `anthropic/claude-opus-4.8` |
| Fast local operator | `hermes-qwen32` | `qwen35-mtp` | `qwen35-9b-mtp` |
| Long-context local | `hermes-gemma12b` | `local` | `gemma4:12b-it-qat` |
| Local code-aware MTP | `hermes-qwen36-27b-mtp` | `qwen35-mtp` | `qwen3.6-27b-mtp` |
| Local Qwen MLX 4-bit | `hermes-qwen36-27b-mlx4bit` | `local` | `qwen3.6-27b-mlxf4bit` |
| Local Qwen MLX 8-bit | `hermes-qwen36-27b-mlx8bit` | `local` | `qwen3.6-27b-mlxf8bit` |
| Local Ornith 9B | `hermes-ornith9b` | `local-ornith-9b` | `ornith-1.0-9b-q4` |
| Local Ornith 35B | `hermes-ornith35b` | `local-ornith-35b` | `ornith-1.0-35b-q4` |

Use `hermes-codex-gpt55` for default high-trust coding handoffs, `hermes-sonnet46` for daily paid review and implementation planning, `hermes-opus48` for the hardest architecture or judge pass, `hermes-qwen37plus` for default paid planning and brainstorm synthesis, `hermes-qwen37max` for deeper Qwen reasoning, and `hermes-minimaxm3` for a second implementation opinion. Use `hermes-qwen32` for short local operator/status work, `hermes-gemma12b` for local long-context and vision-adjacent review, and `hermes-qwen36-27b-mtp` when a local code-aware MTP route is available.

Paid profiles use max thinking by default through `agent.reasoning_effort: xhigh`, keep `agent.verify_on_stop: auto`, and carry the `hermes-cli` and `devflow` toolsets cloned from the `mini` profile. Worker/model output is advisory evidence until Dev-Flow verification passes; it is never completion, merge readiness, promotion readiness, or permission to push.

### Capabilities vs Execution Surfaces

Profile names should identify the model or route, not box the model into one job. This applies to every normal model profile: paid, local, Hermes-backed, OpenRouter-backed, and Ollama-backed. A profile can be good for several activities: brainstorming, implementation planning, UI review, code review, architecture judgment, second-opinion debugging, or patch proposal evidence when an explicit patch surface asks for it. The registry should describe those fit signals with capability metadata: context size, `vision`, `thinking`, `code_focus`, `speed_class`, input modalities, tool access, and `tuned_for_archetypes`.

Execution authority belongs to the command surface:

| Surface | What It Means |
|---|---|
| `agent advise` | Advisory evidence from a selected model profile. |
| `agent propose-patch` | A human-invoked patch proposal surface that writes proposal evidence only. |
| `agent run` | Local WorkerEvidence profile run, still evidence until verified. |
| `task run --worker shell` | Stable direct-edit worker runtime inside the isolated task workspace. |
| Hermes profile handoff | Human-selected Hermes run using the profile's toolsets and Dev-Flow-safe instructions. |

Do not make a real model profile name imply a single job like `patch-proposer`, `reviewer`, `planner`, `summarizer`, or `implementer` unless it is deliberately a separate execution-surface wrapper. `hermes-minimaxm3` means MiniMax M3 through Hermes/OpenRouter; `hermes-sonnet46` means Sonnet 4.6 through Hermes/OpenRouter; `hermes-gemma12b` means the local Gemma route. None of these normal profiles is permanently cornered into one job. If Dev-Flow needs a patch proposal, the operator should choose the `agent propose-patch` surface and Dev-Flow should record that surface as the gate.

### UI And Browser Work

UI work splits into two categories:

| Need | Prefer | Why |
|---|---|---|
| Visual screenshot/mockup review | `hermes-sonnet46`, `hermes-opus48`, `hermes-gemma12b` | These profiles are marked vision/screenshot-capable or vision-adjacent. |
| Browser-driven implementation/debugging | `hermes-codex-gpt55` or a shell/Codex worker lane | Browser access is a tool/runtime capability, not just a model capability. |
| UI code review without screenshots | `hermes-sonnet46`, `hermes-qwen37max`, `hermes-minimaxm3`, `hermes-qwen36-27b-mtp` | Text/code capability is enough when evidence is source files and logs. |
| Fast UI status or next-action planning | `hermes-qwen32`, `hermes-qwen37plus` | Low-latency planning without launching a heavy local model. |

If a UI task requires visual evidence, capture the screenshot or browser findings as Dev-Flow evidence first, then pick a profile with `vision=true` or `screenshot` in `input_modalities`. If a task requires live browser interaction, choose a worker/runtime that actually has browser tooling; do not assume a raw OpenRouter model can browse just because it is strong.

Only one local model may run at a time on a machine. Dev-Flow's local-model runtime lock is global across local providers/models, so a second local model run must wait or fail clearly instead of competing for RAM/Metal resources.

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

Hermes cron jobs are allowed only as bounded status/reporting loops unless Josh explicitly approves a separate mutation command. When advisory is explicitly enabled for a cron profile, the default bounded planning call is one Qwen Plus evidence run:

```bash
devflow agent advise --profile hermes-qwen37plus --job gap-analysis --json
```

The cron heartbeat should gather bounded evidence first: `devflow status --json`, `devflow supervisor packet --json`, `devflow git status`, the latest verification-ledger summary, and targeted stale-context search results. The advisory run may write recommendation evidence under `.devflow/reports/agent-advisory-runs/<run_id>/`, including an exact suggested `devflow task create ...` command, but Hermes must not execute that suggestion. Deep advisory runs require explicit job/profile selection, not automatic escalation. `devflow agent propose-patch` is human-direct patch evidence only; it is not Hermes-delegable and must never be run from unattended Hermes automation.

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

The Hermes `~/.hermes/config.yaml` may have a `model_routing` section that routes tasks to the best model based on keyword patterns. Dev-Flow must not treat another Mac's model map as authority. Current model availability comes from:

- `~/.hermes/config.yaml`
- `~/.hermes/profiles/*/config.yaml`
- local `/v1/models` responses from Hermes/custom OpenAI-compatible endpoints
- `devflow agent catalog --json`
- `devflow supervisor policy --json`

The current Dev-Flow routing surface is:

| Role | Provider | Model | Notes |
|---|---|---|---|
| Default coding handoff | `openai-codex` | `gpt-5.5` | `hermes-codex-gpt55`; subscription profile, not OpenRouter. |
| Daily paid review/planning | `openrouter` | `anthropic/claude-sonnet-4.6` | `hermes-sonnet46`; balanced paid reviewer/implementer. |
| Deep judge/architecture | `openrouter` | `anthropic/claude-opus-4.8` | `hermes-opus48`; reserve for high-value design and review. |
| Paid Qwen planning | `openrouter` | `qwen/qwen3.7-plus` | `hermes-qwen37plus`; default paid brainstorm/planning. |
| Paid Qwen depth | `openrouter` | `qwen/qwen3.7-max` | `hermes-qwen37max`; deeper Qwen coding/reasoning. |
| Alternative paid coding opinion | `openrouter` | `minimax/minimax-m3` | `hermes-minimaxm3`; second implementation lens. |
| Local default / Telegram / read-only planning | `custom:hermes-qwen32` | `qwen35-9b-mtp` | `hermes-qwen32`; prompt-cache-enabled local endpoint. |
| Long-context local | `local` | `gemma4:12b-it-qat` | `hermes-gemma12b`; local long-context and vision-adjacent review. |
| Local code-aware MTP | `qwen35-mtp` | `qwen3.6-27b-mtp` | `hermes-qwen36-27b-mtp`; local code-aware fallback when available. |

### Fallback behavior

Fallback chains activate only when Dev-Flow or Hermes has explicit evidence that the fallback exists on the current machine and fits the current RAM class:

- the primary model is rate-limited or unreachable
- the model lacks required capabilities
- `devflow agent catalog --json` marks the fallback as allowed for the machine

### Mid-session model switching

Use Hermes slash commands to switch models without restarting:

```
/model               # Interactive model picker
/model qwen35-9b-mtp                       # Switch to local Qwen 3.5 MTP default
/model qwen/qwen3.7-plus                  # Switch to paid Qwen Plus planning
/model anthropic/claude-sonnet-4.6        # Switch to paid Sonnet daily review
/model anthropic/claude-opus-4.8          # Switch to paid Opus deep judge
/model gemma4:12b-it-qat                  # Switch to local long-context Gemma
```

For vision tasks that fail because the chat model lacks vision:
1. Attach the image with `/image /path/to/screenshot.png`
2. Switch to the retained local vision-adjacent profile when available: `/model gemma4:12b-it-qat`
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
hermes -p hermes-qwen37plus chat -q "Draft a bounded implementation plan"
hermes -p hermes-opus48 chat -q "Judge this architecture tradeoff"
hermes -p hermes-qwen32 chat -q "Summarize current Dev-Flow status"
```

## Non-Goals

This integration does not add a Hermes worker adapter, provider-backed task-run execution, a dashboard server, a database, autonomous routing, hidden memory, or a competing orchestration loop. OpenRouter and local advisory lanes are Dev-Flow-owned report evidence that Hermes may schedule only under the bounded cron rule above. Future non-shell worker runtime work must follow the registry and adapter sequence documented in the active architecture notes.
