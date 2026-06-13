# Milestone 14A Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dogfood the Milestone 14 goal loop and run release-readiness gates without expanding runtime scope.

**Architecture:** This plan uses existing Dev-Flow CLI surfaces as the system under test. It writes only planning/handoff docs plus ignored `.devflow/` evidence unless a gate exposes a narrow control-room defect that must be fixed.

**Tech Stack:** Python CLI, pytest, Dev-Flow filesystem state, ignored `.devflow/` evidence artifacts, Markdown docs.

---

### Task 1: Baseline Goal-Loop Dogfood

**Files:**
- Modify only if needed: `.devflow/goals/G-0001/goal-state.yaml` (ignored runtime state)
- Evidence: `.devflow/freshness/latest.json`

- [ ] **Step 1: Run the baseline freshness loop**

Run:

```bash
PYTHONPATH=src:. .venv/bin/devflow freshness loop --json
```

Expected: exit 0 if all goals have lifecycle state, or exit 2 with a `needs_human_decision` finding for a pre-existing missing lifecycle state.

- [ ] **Step 2: Repair deferred missing lifecycle state if present**

If the only missing lifecycle finding is `G-0001-lifecycle-missing`, run:

```bash
PYTHONPATH=src:. .venv/bin/devflow goal block G-0001 --reason "Deferred after Milestone 14A; Hermes rollout is not the active next lane, and multi-project control room is the next handoff."
```

Expected: command exits 0 and writes ignored lifecycle evidence under `.devflow/goals/G-0001/`.

- [ ] **Step 3: Rerun the freshness loop**

Run:

```bash
PYTHONPATH=src:. .venv/bin/devflow freshness loop --json
```

Expected: no missing lifecycle finding remains. Any remaining findings are recorded as risks instead of hidden.

### Task 2: Bounded Freshness Run Evidence

**Files:**
- Evidence: `.devflow/freshness/control-runs/**`
- Evidence: `~/.devflow/freshness/control-runs/**` for all-projects output

- [ ] **Step 1: Run bounded local freshness iterations**

Run:

```bash
PYTHONPATH=src:. .venv/bin/devflow freshness run --max-iterations 3 --json
```

Expected: command exits 0, stops on stable state or an explicit human decision, and writes a control-run report.

- [ ] **Step 2: Run bounded all-projects freshness iterations**

Run:

```bash
PYTHONPATH=src:. .venv/bin/devflow freshness run --all-projects --max-iterations 1 --json
```

Expected: command exits 0 or reports registered-project access issues as human-decision evidence without crashing.

### Task 3: Release-Readiness Evidence

**Files:**
- Evidence: `.devflow/dogfood/runs/**`
- Evidence: `.devflow/release-readiness/**` if written by the command
- Evidence: `/tmp/devflow-milestone-14a-pytest.log`
- Evidence: `/tmp/devflow-milestone-14a-stale-context.log`

- [ ] **Step 1: Run full pytest and capture evidence**

Run:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest > /tmp/devflow-milestone-14a-pytest.log 2>&1
```

Expected: exit 0 and a final summary with zero failures.

- [ ] **Step 2: Run stale-context scan and capture evidence**

Run:

```bash
PYTHONPATH=src:. .venv/bin/python - <<'PY' > /tmp/devflow-milestone-14a-stale-context.log
import subprocess
from devflow.control_room.release_readiness import STALE_CONTEXT_COMMAND

result = subprocess.run(
    STALE_CONTEXT_COMMAND,
    shell=True,
    text=True,
    capture_output=True,
    check=False,
)
print(result.stdout, end="")
print(result.stderr, end="")
PY
```

Expected: no active poison-context matches. The evidence log is empty.

- [ ] **Step 3: Run production-readiness dogfood**

Run:

```bash
PYTHONPATH=src:. .venv/bin/devflow dogfood run --suite production-readiness
```

Expected: exits 0 and meets the Silver threshold.

- [ ] **Step 4: Run operating-layer visual QA fallback artifact generation**

Run:

```bash
PYTHONPATH=src:. .venv/bin/devflow operating-layer visual-qa --write-current
```

Expected: exits 0 and writes current visual QA artifacts.

- [ ] **Step 5: Run release-readiness gate**

Run:

```bash
PYTHONPATH=src:. .venv/bin/devflow release readiness --pytest-evidence /tmp/devflow-milestone-14a-pytest.log --stale-context-evidence /tmp/devflow-milestone-14a-stale-context.log
```

Expected: exits 0 with all required gates passing.

### Task 4: Docs And Handoff

**Files:**
- Modify: `docs/roadmap.md`
- Modify: `docs/control-room-mvp.md`
- Modify: `docs/mvp-contract.md`
- Create: `docs/handoffs/2026-06-13-multi-project-control-room-next.md`

- [ ] **Step 1: Update active roadmap status**

Record Milestone 14A as a hardening/release-readiness slice after Milestone 14. Mark multi-project control room as the next planned slice.

- [ ] **Step 2: Update active priority callouts**

Update `docs/control-room-mvp.md` and `docs/mvp-contract.md` current-priority callouts so future agents do not keep re-running Milestone 14 planning.

- [ ] **Step 3: Write the next-agent handoff**

Create `docs/handoffs/2026-06-13-multi-project-control-room-next.md` using `docs/handoff-template.md`. The handoff must have one next safe action: start a spec for the multi-project control room slice.

### Task 5: Final Verification And Checkpoint

**Files:**
- No source edits unless previous gates forced a narrow fix.

- [ ] **Step 1: Check whitespace**

Run:

```bash
git diff --check
```

Expected: no output, exit 0.

- [ ] **Step 2: Check Dev-Flow git status**

Run:

```bash
PYTHONPATH=src:. .venv/bin/devflow git status
```

Expected: clean or only planned docs pending before checkpoint.

- [ ] **Step 3: Checkpoint**

Run:

```bash
PYTHONPATH=src:. .venv/bin/devflow git checkpoint --message "docs: harden goal loop release readiness" --yes
```

Expected: checkpoint commit succeeds.

- [ ] **Step 4: Confirm post-checkpoint state**

Run:

```bash
PYTHONPATH=src:. .venv/bin/devflow git status
```

Expected: clean `main`. Push only after explicit human approval.
