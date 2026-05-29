# /devflow

Legacy alias only. Prefer `/devmode` for all software engineering tasks.

When this workflow is invoked, activate DevMode and output exactly one confirmation line:

```text
DevMode loaded: token optimization, repo discipline, read-only/implementation gating.
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

## Steps

### 1. Intake & Mode Gate
Classify the task and classify the mode before taking any action:
- **Read-only mode**: audit, review, investigate, explain, plan, summarize, or unclear write permission. **Do not edit, stage, commit, or create files.** Use targeted searches and compact findings only.
- **Implementation mode**: fix, build, update, apply, or explicit permission to edit. Edit only relevant files, run targeted verification, and commit only when permitted and verification passes.

*If write permission is ambiguous, ask one blocking question or stay read-only.*

### 2. Context & Token Budget
- Search before broad reads.
- Target specific sections before opening full files.
- No repeated context, transcript bloat, or summaries.
- No ceremonial progress narration or skill-loading announcements.
- Stop when the next safe action is obvious.

### 3. Route to DevMode Skills
Invoke relevant or requested skills BEFORE any response or action. Even a 1% chance a skill might apply means you should check it.
- Use `devmode:using-devmode` as the master bootstrap.
- Route to specific skills under `.agent/skills/` (e.g. `devmode:test-driven-development` for implementation, `devmode:systematic-debugging` for bugs, `devmode:token-budget` for context rationing).

### 4. Silent Work Mode & Output
Run DevMode silently. Do not narrate the workflow. Avoid progress phrases.

Report only after all steps are complete. Omit fields that are empty or not relevant. Use this format:

```text
Decision:
Files changed:
Verification:
Risks:
Next safe action:
```
