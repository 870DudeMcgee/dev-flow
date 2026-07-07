# /devflow-engineering

Activate DevFlow disciplined engineering workflow for the current task.

Output exactly one line:

```text
DevFlow workflow loaded: token optimization, repo discipline, read-only/implementation gating.
```

Then continue silently. Do not output a skills-used line.

---

## 🛡️ The Four Iron Laws

```text
NO ACTION WITHOUT MODE CLASSIFICATION FIRST
NO BROAD READS WITHOUT TARGETED SEARCH FIRST
NO CODE WITHOUT FAILING TESTS FIRST
NO COMPLETION CLAIMS WITHOUT FRESH VERIFICATION EVIDENCE
```

---

## ⚙️ Gating & Routing

### 1. Task Intake & Mode Gate
Classify the task and classify the mode before taking any action:
- **Read-only mode**: audit, review, investigate, explain, plan, summarize, or unclear write permission. **Do not edit, stage, commit, or create files.** Use targeted searches and compact findings only.
- **Implementation mode**: fix, build, update, apply, or explicit permission to edit. Edit only relevant files, run targeted verification, and commit only when permitted and verification passes.

*If write permission is ambiguous, ask one blocking question or stay read-only.*

### 2. Route to Relevant Skills
Invoke relevant or requested skills BEFORE any response or action. Even a 1% chance a skill might apply means you should check it.
- Read `AGENTS.md` and `docs/README.md` for repo-local routing.
- Route to specific skills under `.agent/skills/` only when they fit the task; do not load quarantined docs as active authority.

### 3. Silent Work Mode & Output
Run the workflow silently. Do not narrate the workflow. Avoid progress phrases.

Report only after all steps are complete. Omit fields that are empty or not relevant. Use this format:

```text
Decision:
Files changed:
Verification:
Risks:
Next safe action:
```