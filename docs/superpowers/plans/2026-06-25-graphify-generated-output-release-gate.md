# Graphify Generated Output Release Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Resolve the release gate blockage caused by untracked generated Graphify output while preserving Graphify as local architecture evidence.

**Architecture:** Treat `graphify-out/` as generated evidence, not product source. Add a root-scoped ignore rule, commit only that policy change, then rerun Dev-Flow clean-status and release-readiness gates from a clean tree. Do not delete, version, push, or promote as part of this plan.

**Tech Stack:** Git, `.gitignore`, Dev-Flow CLI, `scripts/release-check.sh`, captured `.devflow/release/candidate-5-*` evidence.

---

## Current State

Start from this repository state:

- Branch: `main`
- Current head: `b8acf94 docs: checkpoint control room cleanup phase`
- `main` is 24 commits ahead of `origin/main`
- After this plan is saved, normal `git status --short` may show this plan document plus `?? graphify-out/`
- `graphify-out/` is generated evidence and is not tracked
- `.gitignore` does not currently ignore `graphify-out/`
- `scripts/release-check.sh` and `devflow release readiness` are blocked only because Git status is dirty

Important policy from `AGENTS.md` and architecture docs:

- Graphify output is evidence, not product authority.
- Commit lightweight metrics and checkpoint docs, not the full generated directory.
- Do not push, publish, or promote without explicit human approval.

## File Structure

- Modify `.gitignore`: add a root-scoped ignore rule for generated Graphify output.
- No source code changes.
- No test code changes.
- Do not add `graphify-out/`.
- Do not delete `graphify-out/`; keeping local generated evidence is fine once it is ignored.

---

### Task 0: Commit This Plan Document

**Files:**
- Create: `docs/superpowers/plans/2026-06-25-graphify-generated-output-release-gate.md`

- [ ] **Step 1: Check whether the plan document is untracked**

Run:

```bash
git status --short
```

Expected before committing the plan:

```text
?? docs/superpowers/plans/2026-06-25-graphify-generated-output-release-gate.md
?? graphify-out/
```

If the plan file is already committed and only `?? graphify-out/` appears, skip to Task 1.

- [ ] **Step 2: Commit only the plan document**

Run:

```bash
git add docs/superpowers/plans/2026-06-25-graphify-generated-output-release-gate.md
git diff --cached --check
git diff --cached --name-only
git commit -m "docs: plan graphify generated output release gate"
```

Expected staged file list:

```text
docs/superpowers/plans/2026-06-25-graphify-generated-output-release-gate.md
```

- [ ] **Step 3: Confirm only Graphify output remains dirty**

Run:

```bash
git status --short
git rev-parse --short HEAD
```

Expected status:

```text
?? graphify-out/
```

The short SHA will be the new plan commit, not `b8acf94`.

---

### Task 1: Confirm The Blocker Is Exactly Graphify Output

**Files:**
- Read: `.gitignore`
- Read: `graphify-out/`
- Read: `.devflow/release/`

- [ ] **Step 1: Confirm worktree status**

Run:

```bash
git status --short
git rev-parse --short HEAD
```

Expected:

```text
?? graphify-out/
```

If any source, test, doc, `.gitignore`, or staged file appears, stop and inspect it before continuing.

- [ ] **Step 2: Confirm `graphify-out/` is not tracked**

Run:

```bash
git ls-files graphify-out
```

Expected: no output.

If this command prints any path, stop. Ignoring a tracked path will not fix the release gate, and the plan must be revised.

- [ ] **Step 3: Confirm the generated output is not already ignored**

Run:

```bash
git check-ignore -v graphify-out/GRAPH_REPORT.md graphify-out/graph.json
```

Expected: exit code `1` and no output, because the files are not ignored yet.

- [ ] **Step 4: Confirm captured release evidence exists**

Run:

```bash
for path in \
  .devflow/release/candidate-5-full-pytest.log \
  .devflow/release/candidate-5-stale-context.log \
  .devflow/release/candidate-5-dogfood.log \
  .devflow/release/candidate-5-visual-qa.log
do
  test -s "$path" || { echo "missing evidence: $path"; exit 1; }
done
```

Expected: no output.

If any file is missing, stop and rerun the corresponding release evidence command instead of trying to fake readiness.

---

### Task 2: Ignore Root Graphify Output

**Files:**
- Modify: `.gitignore`

- [ ] **Step 1: Add the ignore rule**

Use `apply_patch` to add this block after the existing build/dist ignores and before the macOS section:

```diff
*** Begin Patch
*** Update File: .gitignore
@@
 build/
 dist/
 *.egg-info/
+
+# Generated architecture evidence
+/graphify-out/
 # macOS
 .DS_Store
*** End Patch
```

Expected `.gitignore` result:

```gitignore
build/
dist/
*.egg-info/

# Generated architecture evidence
/graphify-out/

# macOS
.DS_Store
```

- [ ] **Step 2: Verify the ignore rule catches generated files**

Run:

```bash
git check-ignore -v graphify-out/GRAPH_REPORT.md graphify-out/graph.json
```

Expected output includes `.gitignore` and `/graphify-out/` for both paths.

- [ ] **Step 3: Verify normal Git status no longer shows `graphify-out/`**

Run:

```bash
git status --short
git status --ignored --short graphify-out | head -5
```

Expected normal status:

```text
 M .gitignore
```

Expected ignored status includes:

```text
!! graphify-out/
```

- [ ] **Step 4: Run whitespace check**

Run:

```bash
git diff --check
```

Expected: no output.

---

### Task 3: Commit The Ignore Policy

**Files:**
- Modify: `.gitignore`

- [ ] **Step 1: Review the diff**

Run:

```bash
git diff -- .gitignore
```

Expected diff contains only:

```diff
+# Generated architecture evidence
+/graphify-out/
```

- [ ] **Step 2: Stage and commit only `.gitignore`**

Run:

```bash
git add .gitignore
git diff --cached --check
git diff --cached --name-only
git commit -m "chore: ignore graphify generated output"
```

Expected staged file list:

```text
.gitignore
```

Expected commit: a new local commit after `b8acf94`.

- [ ] **Step 3: Confirm clean normal status**

Run:

```bash
git status --short
env PYTHONPATH=src:. .venv/bin/python -m devflow.cli git status
```

Expected:

- `git status --short` prints no output.
- Dev-Flow reports `clean: yes`.
- Dev-Flow reports `safe_for_push: yes` or no longer blocks solely on untracked `graphify-out/`.

If Dev-Flow still reports dirty status, inspect the reported path before continuing.

---

### Task 4: Rerun Formal Release Readiness With Captured Evidence

**Files:**
- Read: `.devflow/release/candidate-5-full-pytest.log`
- Read: `.devflow/release/candidate-5-stale-context.log`
- Read: latest production dogfood run under `.devflow/`
- Read: operating-layer visual QA evidence under `.devflow/` or dogfood artifacts

- [ ] **Step 1: Run release readiness using existing evidence**

Run:

```bash
env PYTHONPATH=src:. .venv/bin/python -m devflow.cli release readiness \
  --pytest-evidence .devflow/release/candidate-5-full-pytest.log \
  --stale-context-evidence .devflow/release/candidate-5-stale-context.log \
  --dogfood-run latest | tee /tmp/devflow-release-readiness-after-graphify-ignore.log
```

Expected output includes:

```text
status: passed
```

and every check is `passed`, especially:

```text
- clean-devflow-git-status: passed
- full-pytest: passed
- dogfood-production-readiness: passed
- operating-layer-visual-qa-evidence: passed
- stale-context-scan: passed
- standard-handoff-report: passed
```

- [ ] **Step 2: Stop if release readiness is blocked**

If readiness is not `passed`, do not push or promote. Read `/tmp/devflow-release-readiness-after-graphify-ignore.log` and fix only the first blocked gate.

---

### Task 5: Rerun The Release Check Script From A Clean Tree

**Files:**
- Read: `scripts/release-check.sh`
- Generated ignored output may appear under `dist/`

- [ ] **Step 1: Run the release script**

Run:

```bash
scripts/release-check.sh | tee /tmp/devflow-release-check-after-graphify-ignore.log
```

Expected final output includes:

```text
SUCCESS: Dev-Flow is fully validated and ready for release!
```

This script may rerun full pytest and packaging smoke checks. Do not interrupt it unless it hangs or fails.

- [ ] **Step 2: Confirm the worktree remains clean**

Run:

```bash
git status --short
env PYTHONPATH=src:. .venv/bin/python -m devflow.cli git status
```

Expected:

- Normal Git status prints no output.
- Dev-Flow reports clean status.
- Ignored generated directories such as `graphify-out/` and `dist/` do not block release readiness.

---

### Task 6: Report The Promotion Decision Point

**Files:**
- No file changes.

- [ ] **Step 1: Summarize the final state**

The handoff must include:

- New commit SHA for `chore: ignore graphify generated output`
- `git status --short`: clean
- Dev-Flow git status: clean and safe for push/promotion
- `devflow release readiness`: passed
- `scripts/release-check.sh`: passed
- Remaining warning, if still present: unknown pytest marks `ui_browser` and `ui_browser_live`

- [ ] **Step 2: Stop before push unless explicitly approved**

Do not run raw `git push origin main`.

Do not run `devflow push-main` unless the human explicitly approves pushing the cleanup phase.

If the human approves push after the gates pass, use the Dev-Flow command:

```bash
env PYTHONPATH=src:. .venv/bin/python -m devflow.cli push-main
```

Expected: push succeeds and `main` is no longer ahead of `origin/main`.

## Done State

This plan is done when:

- `.gitignore` has a root-scoped `/graphify-out/` generated-evidence rule.
- This plan document is either committed as its own docs commit or intentionally removed before release gates run.
- `graphify-out/` remains on disk if useful, but is ignored by Git.
- The ignore policy is committed as `chore: ignore graphify generated output`.
- Normal `git status --short` is clean.
- Dev-Flow git status no longer blocks on untracked Graphify output.
- `devflow release readiness` passes using the captured candidate-5 evidence.
- `scripts/release-check.sh` passes from the clean tree.
- No push or promotion has been performed unless the human explicitly approves it after the gates pass.
