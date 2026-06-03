# Dev-Flow & DevMode Agent Operating Rules

All agent operations in this repository are governed by the canonical [docs/devmode-contract.md](docs/devmode-contract.md).

DevMode guides behavior only inside the host tool’s allowed instruction hierarchy and does not outrank higher-level platform, system, developer, safety, or explicit user instructions.

Local checkout note: Josh's current canonical checkout is `/Users/jewelbait/Desktop/Local AI Dev Team`. The old local path `/Users/jewelbait/Desktop/DevFlow` is quarantined and must not be used for current work. Do not assume every user's checkout folder is named `DevFlow`; use the actual local path in context or a neutral placeholder such as `<repo-root>`.

---

## 🎯 Dev-Flow Current Product Target

Dev-Flow is being built into a simpler product: a local-first control room for parallel AI coding workers.

Do not use the archived legacy workflow as process authority. Do not require old task files, claim rituals, staged ceremonies, local-model delegation, memory, DAGs, traces, or old patch gates before doing ordinary work.

Dev-Flow owns:
- Tasks & isolated workspaces
- Locks and ownership
- Status, questions, logs, and reports
- Verification & merge readiness

Workers are replaceable. The current code-changing runtime supports **shell workers**; `devflow task local` is a narrow local Ollama evidence wrapper for Qwen/Gemma prompt-response capture and does not edit, verify, route, promote, or call remote provider APIs. The next architecture direction is documented in [docs/architecture/agent-registry-and-adapter-runtime.md](docs/architecture/agent-registry-and-adapter-runtime.md), with future task-fit/context routing design in [docs/architecture/agent-selection-and-context-routing.md](docs/architecture/agent-selection-and-context-routing.md), but neither is active runtime behavior yet.

### First Milestone Commands
```bash
devflow init
devflow doctor
devflow task create "title"
devflow task list
devflow task show <task_id>
devflow task run <task_id> --worker shell -- <command>
devflow task local <task_id> --worker qwen-planner
devflow task local <task_id> --worker gemma-reviewer --input-worker qwen-planner
devflow dashboard
```

Do not implement Aider, Hermes worker/runtime adapters, OpenCode, memory, complex scheduling, task-fit/context routing runtime, or autonomous routing. Hermes may be documented as an external read-only operator/chat gateway over supervisor-safe commands only. Future non-shell work beyond the narrow local Ollama evidence wrapper must follow the registry sequence: architecture doc, registry loading, agent list/show/packet commands, manual adapter, shell alignment, deterministic task-fit/context estimation, context pack building, then local/OpenAI-compatible/native provider adapters and conservative routing.

---

## ⚡ Active Execution Rules

Before making any code changes, perform these checks:

1. **Code Boundary Check:** All active control-room development must be constrained entirely inside `src/devflow/control_room/`. Legacy software-factory files are quarantined in `src/devflow/_legacy/` and top-level shims are compatibility bridges. **Never write new features under top-level modules or `_legacy/`.** Read [docs/agent-handoff.md](docs/agent-handoff.md) for details.
2. Read [PRODUCT_NORTH_STAR.md](PRODUCT_NORTH_STAR.md) and check your plan against its *Periodic Self-Check* section.
3. Read [docs/control-room-mvp.md](docs/control-room-mvp.md).
4. Read [docs/token-optimization.md](docs/token-optimization.md) and invoke `devmode:token-budget` to manage active context and search policies.
5. Inspect only the smallest relevant implementation files.
6. Preserve useful code that supports the control-room MVP.
7. Bypass old workflow machinery that conflicts with the MVP.
8. Keep changes focused and verify them.

---

## 🛡️ One Writer At A Time

Only one developer agent may edit files in the repository at a time. Other agents may review, inspect, or plan in a read-only capacity. The worktree must be clean and verified before switching active writers.

## DevMode Git Bridge

Dev-Flow projects use DevMode as the agent discipline layer. When `.devflow/` exists, agents must apply DevMode `using-devmode` and `workspace-isolation`. Git-changing actions must go through Dev-Flow commands where available: `devflow git status`, `devflow sync-main`, `devflow task promote-preview`, `devflow task promote`, and `devflow push-main`. Do not run raw `git push origin main`, raw promotion merges, or conflict-resolution rebases unless the human explicitly authorizes it.

---

## ✅ Milestone Closure Discipline

Every major feature, milestone, or direction change must end with a clean checkpoint:

1. Update the active docs first so future agents do not inherit stale or conflicting context.
2. Remove junk, outdated archive references, and confusing dead plans from the active repo.
3. Run focused verification plus any broader suite needed for the blast radius.
4. Confirm the tree is clean after commit.
5. Merge the work to `main` and push the remote branch/mainline when explicitly approved.
6. Write a compact handoff using [docs/handoff-template.md](docs/handoff-template.md), with one concrete next safe action.

Archived or quarantined material must stay outside the active repo unless it is intentionally restored as current, non-archived source.

---

## ⚠️ Poison Context Warning

Old direction is not harmless. Conflicting docs, stale plans, archived rituals, obsolete command lists, and legacy architecture notes are **poison context**: they cause future agents to confidently build the wrong product.

When you find poison context in the active repo:

1. Remove it if it is junk, obsolete, or archived material.
2. Rewrite it if the file is still useful but points at the wrong direction.
3. Quarantine it outside the active repo if history must be kept.
4. Mark any intentionally retained historical note as non-authoritative.
5. Re-run stale-context searches before committing.

Do not leave "maybe useful later" context in active docs. If it is not current authority and it can steer implementation, it must be cleaned up before the milestone is closed.

---

## 🤫 Silent Work Mode

Operate silently without narration or progress commentary. Speak only to ask a blocking question, report a verification failure, or document a risk that changes the next safe action.

---

## Standard Handoff Format

Every task completion report, status update, or shift handoff must use the standard headings defined in [docs/handoff-template.md](docs/handoff-template.md). Keep handoffs short enough to paste into a new chat without dragging the entire previous conversation forward.

## Status

[complete | in-progress | blocked | needs-review | failed]

## Files Changed

- path/to/file (summary of what changed)

## Verification

- `command run`: pass/fail + actual output logs

## Risks

- Specific technical risks, limitations, or side-effects

## Next Safe Action

- The single, concrete next action to take
