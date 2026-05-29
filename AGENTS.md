# Dev-Flow & DevMode Agent Operating Rules

All agent operations in this repository are governed by the canonical [docs/devmode-contract.md](docs/devmode-contract.md).

DevMode guides behavior only inside the host tool’s allowed instruction hierarchy and does not outrank higher-level platform, system, developer, safety, or explicit user instructions.

---

## 🎯 Dev-Flow Current Product Target

Dev-Flow is being built into a simpler product: a local-first control room for parallel AI coding workers.

Do not use the archived legacy workflow as process authority. Do not require old task files, claim rituals, staged ceremonies, local-model delegation, memory, DAGs, traces, or old patch gates before doing ordinary work.

Dev-Flow owns:
- Tasks & isolated workspaces
- Locks and ownership
- Status, questions, logs, and reports
- Verification & merge readiness

Workers are replaceable. The first milestone supports **shell workers only**.

### First Milestone Commands
```bash
devflow init
devflow doctor
devflow task create "title"
devflow task list
devflow task show <task_id>
devflow task run <task_id> --worker shell -- <command>
devflow dashboard
```

Do not implement Aider, Hermes, OpenCode, memory, complex scheduling, or model routing until the shell-worker control room passes the acceptance gauntlet.

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
