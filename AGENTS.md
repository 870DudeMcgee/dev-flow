# Dev-Flow & DevMode Agent Operating Rules

This repository combines the high-discipline **DevMode** framework with the **Dev-Flow** control room kernel development goals.

All agent operations in this repository are subject to these rules.

---

## 🛡️ The Four Iron Laws

DevMode-compliant agents are bound by these four immutable laws:

```text
NO ACTION WITHOUT MODE CLASSIFICATION FIRST
NO BROAD READS WITHOUT TARGETED SEARCH FIRST
NO CODE WITHOUT FAILING TESTS FIRST
NO COMPLETION CLAIMS WITHOUT FRESH VERIFICATION EVIDENCE
```

Any violation of these rules requires the agent to **pause, correct the non-compliant approach, and re-verify the task systematically**.

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

## ⚙️ Execution Gating & Budgeting

### 1. Mode Gate
Classify the task before taking any action:
- **Read-only mode**: audit, review, investigate, explain, plan, summarize, or unclear write permission. **Do not edit, stage, commit, or create files.** Use targeted searches and compact findings only.
- **Implementation mode**: fix, build, update, apply, or explicit permission to edit. Edit only relevant files, run targeted verification, and commit only when permitted and verification passes.

*If write permission is ambiguous, ask one blocking question or stay read-only.*

### 2. Token Budget (Always On)
- Search before broad reads.
- Target specific sections before opening full files.
- No repeated context, transcript bloat, or summaries.
- No ceremonial progress narration or skill-loading announcements.
- Stop when the next safe action is obvious.

### 3. One Writer At A Time
Only one agent may edit files at a time. Other agents may review, inspect, or plan. The worktree must be clean before switching writers.

---

## 🔍 Verification & Handoff Protocols

### 1. Verification Before Completion
Never claim done or complete without running verification commands and reading the actual output. **Evidence before assertions always.**

### 2. Silent Work Mode
Run DevMode silently. Use skills internally. Do not narrate the workflow. Avoid phrases like *"I'll..."*, *"I'm going to..."*, *"Let me..."*, *"Completed..."*. Only speak when:
- Asking a blocking question.
- Reporting the final result.
- Reporting a verification failure.
- Reporting a risk that changes the next safe action.

### 3. Handoff Format
Every handoff or task completion report must use this format:

```markdown
## Status
[complete | in-progress | blocked | needs-review | failed]

## Files Changed
- path/to/file (what changed)

## Verification
- `command run`: pass/fail + result

## Risks
- Known issues or limitations

## Next Safe Action
- The single next thing to do
```

---

## 📦 Skill Reference

Specialized disciplines live under [skills/](file:///Users/jewelbait/Desktop/Local%20AI%20Dev%20Team/skills) and [.agent/skills/](file:///Users/jewelbait/Desktop/Local%20AI%20Dev%20Team/.agent/skills).
Each skill has a `SKILL.md` with YAML metadata for auto-discovery. See `devmode:using-devmode` for the master bootstrap.
