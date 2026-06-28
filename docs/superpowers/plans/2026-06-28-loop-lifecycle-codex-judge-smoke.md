# Loop Lifecycle Codex Judge Smoke Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove the repaired Loop-Goal-Script lifecycle with a disposable smoke repo, then prepare a gated Codex 5.5 Dev-Flow architecture rehab run with Codex 5.5 judge enabled for worker and judge paths.

**Architecture:** Dev-Flow's architecture skill wrapper prepares goal files and explicit Loop-Goal-Script commands; Loop-Goal-Script owns worker execution, handoff extraction, status/watch/control, and judge execution. Smoke runs stay cheap with `--worker local-fast` and `--no-judge`; rehab runs use `--judge-profile dfcodex55` for both `local-fast` and `codex55` workers.

**Tech Stack:** Python 3, pytest, Hermes profiles `dflocalfast` and `dfcodex55`, Loop-Goal-Script, Dev-Flow architecture rehab skill scripts, Dev-Flow operating layer.

---

## Current State To Preserve

- Primary repo: `/Users/josh/Desktop/Dev-Flow`
- Loop engine repo: `/Users/josh/Desktop/Loop Goal Script`
- The Dev-Flow worktree may contain unrelated user or agent changes, including untracked architecture rehab skill files. Do not revert them.
- The Loop Goal Script worktree has intended edits from the previous agent: judge-profile plumbing, PID-only status support, stall/shutdown behavior, launcher path fixes, dashboard import fallback, and tests.
- Do not push, publish, open PRs, promote, merge, or commit unless the operator explicitly asks.
- Do not commit generated `graphify-out/`.
- Do not use `/Users/jewelbait/Desktop/DevFlow`; that path is quarantined.

## File Responsibilities

- `/Users/josh/Desktop/Dev-Flow/skills/improve-codebase-architecture/scripts/start_rehab_loop.py`: prepares smoke or rehab goal text, selects worker profile, selects judge profile, preflights real starts, and prints the Loop-Goal-Script command.
- `/Users/josh/Desktop/Dev-Flow/skills/improve-codebase-architecture/scripts/rehab_loop_status.py`: summarizes Loop-Goal-Script status/watch output and latest scorecard evidence for a repo/slug.
- `/Users/josh/Desktop/Dev-Flow/skills/improve-codebase-architecture/LOOP-GOAL-SCRIPT-INTEGRATION.md`: operator-facing integration contract.
- `/Users/josh/Desktop/Dev-Flow/tests/test_architecture_rehab_skill_scripts.py`: regression tests for the wrapper and status scripts.
- `/Users/josh/Desktop/Loop Goal Script/loop.py`: loop runtime, CLI, status/watch/control, background launch, judge behavior.
- `/Users/josh/Desktop/Loop Goal Script/test_cli.py`: CLI, status, stop, stall, launcher, and judge-profile regression tests.
- `/Users/josh/Desktop/Loop Goal Script/test_watch.py`: watch/status regression tests.
- `/Users/josh/Desktop/Loop Goal Script/test_task_store_sync.py`: loop-to-task-store sync tests.
- `/Users/josh/Desktop/Loop Goal Script/test_loop_cockpit.py`: cockpit smoke tests.
- `/Users/josh/Desktop/Loop Goal Script/launch_control_center.sh`: opens Control Center.
- `/Users/josh/Desktop/Loop Goal Script/launch_cockpit.sh`: opens Cockpit.

---

### Task 1: Re-establish Baseline And Confirm No Orphan Workers

**Files:**
- Read: `/Users/josh/Desktop/Dev-Flow/AGENTS.md`
- Read: `/Users/josh/Desktop/Dev-Flow/docs/superpowers/plans/2026-06-28-loop-lifecycle-codex-judge-smoke.md`
- Inspect only: `/Users/josh/Desktop/Dev-Flow`
- Inspect only: `/Users/josh/Desktop/Loop Goal Script`

- [ ] **Step 1: Read repo instructions**

Run:

```bash
sed -n '1,240p' /Users/josh/Desktop/Dev-Flow/AGENTS.md
```

Expected: output includes `Dev-Flow Agent Guide`, current product instructions, automation posture, and verification policy.

- [ ] **Step 2: Inspect worktree status without changing files**

Run:

```bash
cd /Users/josh/Desktop/Dev-Flow
git status --short
cd /Users/josh/Desktop/Loop\ Goal\ Script
git status --short
```

Expected: Dev-Flow may show modified/untracked architecture skill files. Loop Goal Script should show modified loop/dashboard/test files from the previous repair. Do not revert any unrelated changes.

- [ ] **Step 3: Confirm no orphan loop or model processes**

Run:

```bash
ps -axo pid,ppid,pgid,etime,command | grep -E '(/Users/josh/Desktop/Loop Goal Script/loop.py start|hermes -p dflocalfast|hermes -p dfcodex55)' | grep -v grep || true
```

Expected: no output. If output includes a live `loop.py start` or `hermes -p dflocalfast`/`hermes -p dfcodex55`, stop and identify it before launching a new loop:

```bash
/Users/josh/Desktop/Loop\ Goal\ Script/loop.py status
```

- [ ] **Step 4: Confirm Loop-Goal-Script sees no active loops**

Run:

```bash
/Users/josh/Desktop/Loop\ Goal\ Script/loop.py status
```

Expected:

```text
No active loops.
```

If status lists a running loop, do not start the smoke test until the operator confirms whether to stop, pause, or observe it.

---

### Task 2: Run Focused Regression Tests Before The Live Smoke

**Files:**
- Test: `/Users/josh/Desktop/Loop Goal Script/test_cli.py`
- Test: `/Users/josh/Desktop/Loop Goal Script/test_watch.py`
- Test: `/Users/josh/Desktop/Loop Goal Script/test_task_store_sync.py`
- Test: `/Users/josh/Desktop/Loop Goal Script/test_loop_cockpit.py`
- Test: `/Users/josh/Desktop/Dev-Flow/tests/test_architecture_rehab_skill_scripts.py`

- [ ] **Step 1: Run Loop-Goal-Script touched suite**

Run:

```bash
cd /Users/josh/Desktop/Loop\ Goal\ Script
/Users/josh/Desktop/Dev-Flow/.venv/bin/python -m pytest test_cli.py test_watch.py test_task_store_sync.py test_loop_cockpit.py -q
```

Expected: exit 0 and summary contains:

```text
93 passed
```

- [ ] **Step 2: Compile Loop-Goal-Script runtime files**

Run:

```bash
cd /Users/josh/Desktop/Loop\ Goal\ Script
/Users/josh/Desktop/Dev-Flow/.venv/bin/python -m py_compile loop.py loopd control_center.py loop_cockpit.py task_ops.py
```

Expected: exit 0 and no output.

- [ ] **Step 3: Run Dev-Flow architecture rehab script suite**

Run:

```bash
cd /Users/josh/Desktop/Dev-Flow
.venv/bin/python -m pytest tests/test_architecture_rehab_skill_scripts.py -q
```

Expected: exit 0 and summary contains:

```text
10 passed
```

- [ ] **Step 4: Run whitespace checks in both repos**

Run:

```bash
cd /Users/josh/Desktop/Loop\ Goal\ Script
git diff --check
cd /Users/josh/Desktop/Dev-Flow
git diff --check --cached
git diff --check
```

Expected: all commands exit 0 and produce no output.

---

### Task 3: Prepare Disposable Smoke Repo

**Files:**
- Create or overwrite only inside: `/Users/josh/Desktop/Dev-Flow/.devflow/architecture-rehab/smoke-repo`
- Create or overwrite: `/Users/josh/Desktop/Dev-Flow/.devflow/architecture-rehab/smoke-repo/smoke.py`
- Create or overwrite: `/Users/josh/Desktop/Dev-Flow/.devflow/architecture-rehab/smoke-repo/test_smoke.py`

- [ ] **Step 1: Recreate the tiny smoke fixture**

Run:

```bash
cd /Users/josh/Desktop/Dev-Flow
mkdir -p .devflow/architecture-rehab/smoke-repo
cd .devflow/architecture-rehab/smoke-repo
git init
printf 'def add(a, b):\n    return a + b\n' > smoke.py
printf 'from smoke import add\n\ndef test_add():\n    assert add(1, 2) == 3\n' > test_smoke.py
git status --short
```

Expected:

```text
?? smoke.py
?? test_smoke.py
```

- [ ] **Step 2: Verify the smoke fixture locally without the loop**

Run:

```bash
cd /Users/josh/Desktop/Dev-Flow/.devflow/architecture-rehab/smoke-repo
python -m pytest -q
```

Expected:

```text
1 passed
```

If `pytest` is unavailable under `python`, try:

```bash
/Users/josh/Desktop/Dev-Flow/.venv/bin/python -m pytest -q
```

Expected:

```text
1 passed
```

---

### Task 4: Confirm Generated Commands Before Live Smoke

**Files:**
- Read output from: `/Users/josh/Desktop/Dev-Flow/skills/improve-codebase-architecture/scripts/start_rehab_loop.py`
- Goal files will be generated under: `/Users/josh/Desktop/Dev-Flow/.devflow/architecture-rehab/smoke-repo/.devflow/architecture-rehab/goals/`
- Goal files will be generated under: `/Users/josh/Desktop/Dev-Flow/.devflow/architecture-rehab/goals/`

- [ ] **Step 1: Dry-run the smoke command**

Run:

```bash
cd /Users/josh/Desktop/Dev-Flow
.venv/bin/python skills/improve-codebase-architecture/scripts/start_rehab_loop.py \
  --repo .devflow/architecture-rehab/smoke-repo \
  --candidate "Smoke test loop reliability: inspect the tiny repo, run python -m pytest -q if available, write a clean handoff, and do not change files" \
  --worker local-fast \
  --max-iterations 1 \
  --dry-run
```

Expected JSON properties:

```json
{
  "goal_template": "smoke",
  "profile": "dflocalfast",
  "judge_profile": null,
  "started": false,
  "dry_run": true
}
```

Expected command contains:

```text
--profile dflocalfast --no-judge
```

Expected command does not contain:

```text
--judge-profile
```

- [ ] **Step 2: Dry-run the Codex worker rehab command**

Run:

```bash
cd /Users/josh/Desktop/Dev-Flow
.venv/bin/python skills/improve-codebase-architecture/scripts/start_rehab_loop.py \
  --repo . \
  --candidate "Dev-Flow architecture rehab: choose one Graphify-backed Ponytail slice, use subagents only where useful, run focused tests, write scorecard evidence, and stop after one safe slice" \
  --worker codex55 \
  --max-iterations 1 \
  --dry-run
```

Expected JSON properties:

```json
{
  "goal_template": "rehab",
  "profile": "dfcodex55",
  "judge_profile": "dfcodex55",
  "started": false,
  "dry_run": true
}
```

Expected command contains:

```text
--profile dfcodex55 --judge-profile dfcodex55
```

- [ ] **Step 3: Dry-run local-fast rehab judge check**

Run:

```bash
cd /Users/josh/Desktop/Dev-Flow
.venv/bin/python skills/improve-codebase-architecture/scripts/start_rehab_loop.py \
  --repo . \
  --candidate "Dev-Flow architecture rehab local worker judge check" \
  --worker local-fast \
  --max-iterations 1 \
  --dry-run
```

Expected JSON properties:

```json
{
  "goal_template": "rehab",
  "profile": "dflocalfast",
  "judge_profile": "dfcodex55",
  "started": false,
  "dry_run": true
}
```

Expected command contains:

```text
--profile dflocalfast --judge-profile dfcodex55
```

---

### Task 5: Open Or Reuse Operator Views

**Files:**
- Run: `/Users/josh/Desktop/Loop Goal Script/launch_control_center.sh`
- Run: `/Users/josh/Desktop/Loop Goal Script/launch_cockpit.sh`

- [ ] **Step 1: Inspect dashboard processes**

Run:

```bash
ps -axo pid,ppid,pgid,etime,command | grep -E '(control_center.py|loop_cockpit.py)' | grep -v grep || true
```

Expected: zero or more dashboard processes. Dashboard processes are allowed. Do not kill them unless the operator asks.

- [ ] **Step 2: Open Control Center and Cockpit if no usable terminal windows are visible**

Run:

```bash
open -a Terminal /Users/josh/Desktop/Loop\ Goal\ Script/launch_control_center.sh
open -a Terminal /Users/josh/Desktop/Loop\ Goal\ Script/launch_cockpit.sh
```

Expected: Terminal windows open for Control Center and Cockpit. If the scripts exit immediately, run:

```bash
cd /Users/josh/Desktop/Loop\ Goal\ Script
/Users/josh/Desktop/Dev-Flow/.venv/bin/python -m py_compile control_center.py loop_cockpit.py task_ops.py
```

Expected: exit 0. If compile fails, fix the syntax error before continuing.

---

### Task 6: Run Phase 1 Live Smoke

**Files:**
- Goal file generated under: `/Users/josh/Desktop/Dev-Flow/.devflow/architecture-rehab/smoke-repo/.devflow/architecture-rehab/goals/`
- Loop log expected under: `/Users/josh/.hermes/logs/`
- Handoff expected under: `/Users/josh/.hermes/sessions/`
- Smoke repo must remain limited to: `/Users/josh/Desktop/Dev-Flow/.devflow/architecture-rehab/smoke-repo`

- [ ] **Step 1: Start the live smoke**

Run:

```bash
cd /Users/josh/Desktop/Dev-Flow
.venv/bin/python skills/improve-codebase-architecture/scripts/start_rehab_loop.py \
  --repo .devflow/architecture-rehab/smoke-repo \
  --candidate "Smoke test loop reliability: inspect the tiny repo, run python -m pytest -q if available, write a clean handoff, and do not change files" \
  --worker local-fast \
  --max-iterations 1
```

Expected startup evidence:

```text
Profile: dflocalfast
```

Expected command behavior:

```text
--no-judge
```

Forbidden behavior:

```text
qwen-worker
```

- [ ] **Step 2: Watch Loop-Goal-Script global status from a second terminal**

Run:

```bash
/Users/josh/Desktop/Loop\ Goal\ Script/loop.py status
```

Expected during run: a running loop with iteration `0` before first handoff or iteration `1` after handoff.

- [ ] **Step 3: Watch wrapper status after you know the slug**

Use the `loop_slug` printed by `start_rehab_loop.py`. Run:

```bash
cd /Users/josh/Desktop/Dev-Flow
.venv/bin/python skills/improve-codebase-architecture/scripts/rehab_loop_status.py \
  --repo .devflow/architecture-rehab/smoke-repo \
  --slug <loop_slug_from_start_rehab_loop_json>
```

Expected: parseable JSON or text output showing Loop-Goal-Script status/watch information. If the wrapper requires a slug and the loop has not written a handoff, use:

```bash
/Users/josh/Desktop/Loop\ Goal\ Script/loop.py watch <loop_slug_from_start_rehab_loop_json> --once
```

Expected:

```text
iter 0 | next: waiting for first handoff
```

- [ ] **Step 4: Verify pass criteria after the smoke exits**

Run:

```bash
/Users/josh/Desktop/Loop\ Goal\ Script/loop.py status
cd /Users/josh/Desktop/Dev-Flow/.devflow/architecture-rehab/smoke-repo
git status --short
ps -axo pid,ppid,pgid,etime,command | grep -E '(/Users/josh/Desktop/Loop Goal Script/loop.py start|hermes -p dflocalfast|hermes -p dfcodex55)' | grep -v grep || true
```

Expected:

```text
No active loops.
```

Expected smoke repo status:

```text
?? smoke.py
?? test_smoke.py
```

Expected process check: no output.

Pass criteria:

- Loop starts with `--profile dflocalfast`.
- Loop never uses `qwen-worker`.
- One handoff is written.
- Status/watch output is parseable before and after handoff.
- Smoke repo source files are unchanged after fixture creation.
- No orphan `loop.py start`, `hermes -p dflocalfast`, or `hermes -p dfcodex55` process remains.

Stop criteria:

- No handoff appears and no output changes for the configured stall window.
- The run tries `qwen-worker`.
- The run edits outside `/Users/josh/Desktop/Dev-Flow/.devflow/architecture-rehab/smoke-repo`.
- The local endpoint/model fails.
- A process remains after the loop claims completion.

---

### Task 7: If Phase 1 Fails, Fix The Narrow Lifecycle Bug

**Files:**
- Likely modify: `/Users/josh/Desktop/Loop Goal Script/loop.py`
- Likely modify: `/Users/josh/Desktop/Loop Goal Script/test_cli.py`
- Likely modify: `/Users/josh/Desktop/Loop Goal Script/test_watch.py`
- Maybe modify: `/Users/josh/Desktop/Dev-Flow/skills/improve-codebase-architecture/scripts/start_rehab_loop.py`
- Maybe modify: `/Users/josh/Desktop/Dev-Flow/tests/test_architecture_rehab_skill_scripts.py`

- [ ] **Step 1: Classify the failure**

Use this mapping:

```text
qwen-worker used -> Dev-Flow wrapper command/profile bug.
No PID/status before handoff -> Loop-Goal-Script list/status/watch bug.
Stop cannot resolve slug before handoff -> Loop-Goal-Script PID-only slug resolution bug.
Silent process never stops -> Loop-Goal-Script monitor_session stall bug.
Handoff missing but worker exited 0 -> handoff extraction or prompt bug.
Smoke repo files changed unexpectedly -> smoke prompt or worker instruction bug.
Goal file overwritten in fast dry-runs -> Dev-Flow goal filename bug.
```

- [ ] **Step 2: Write one failing regression test for the classified bug**

For a Loop-Goal-Script lifecycle bug, add the smallest test to one of:

```text
/Users/josh/Desktop/Loop Goal Script/test_cli.py
/Users/josh/Desktop/Loop Goal Script/test_watch.py
```

For a Dev-Flow wrapper bug, add the smallest test to:

```text
/Users/josh/Desktop/Dev-Flow/tests/test_architecture_rehab_skill_scripts.py
```

Example for a command/profile regression:

```python
def test_start_rehab_loop_smoke_never_uses_default_qwen_worker(tmp_path: Path) -> None:
    start = _load_script("start_rehab_loop.py")
    repo = tmp_path / "smoke-repo"
    repo.mkdir()
    loop_script = tmp_path / "Loop Goal Script" / "loop.py"
    loop_script.parent.mkdir()
    loop_script.write_text("#!/usr/bin/env python3\n", encoding="utf-8")

    result = start.prepare_rehab_loop(
        repo,
        candidate="Smoke test loop reliability",
        loop_script=loop_script,
        goal_dir=tmp_path / "goals",
        dry_run=True,
    )

    assert "--profile" in result["command"]
    assert "dflocalfast" in result["command"]
    assert "qwen-worker" not in result["command"]
```

- [ ] **Step 3: Run the focused failing test**

For Loop-Goal-Script:

```bash
cd /Users/josh/Desktop/Loop\ Goal\ Script
/Users/josh/Desktop/Dev-Flow/.venv/bin/python -m pytest test_cli.py::test_name_added_in_step_2 -q
```

For Dev-Flow:

```bash
cd /Users/josh/Desktop/Dev-Flow
.venv/bin/python -m pytest tests/test_architecture_rehab_skill_scripts.py::test_name_added_in_step_2 -q
```

Expected before implementation: exit 1 and the assertion proves the observed failure.

- [ ] **Step 4: Implement the smallest code fix**

Edit only the file implicated by the failing test. Do not refactor adjacent behavior. Use `apply_patch`.

- [ ] **Step 5: Run focused test, then touched suite**

For Loop-Goal-Script:

```bash
cd /Users/josh/Desktop/Loop\ Goal\ Script
/Users/josh/Desktop/Dev-Flow/.venv/bin/python -m pytest test_cli.py test_watch.py test_task_store_sync.py test_loop_cockpit.py -q
```

Expected: exit 0.

For Dev-Flow:

```bash
cd /Users/josh/Desktop/Dev-Flow
.venv/bin/python -m pytest tests/test_architecture_rehab_skill_scripts.py -q
```

Expected: exit 0.

- [ ] **Step 6: Rerun Phase 1 live smoke from Task 6**

Expected: all Task 6 pass criteria hold. If a different lifecycle bug appears, repeat Task 7 with a new failing test.

---

### Task 8: Phase 2 Dry-Run Gate

**Files:**
- Generated goal under: `/Users/josh/Desktop/Dev-Flow/.devflow/architecture-rehab/goals/`
- Do not start a model in this task.

- [ ] **Step 1: Run the Phase 2 dry-run**

Run:

```bash
cd /Users/josh/Desktop/Dev-Flow
.venv/bin/python skills/improve-codebase-architecture/scripts/start_rehab_loop.py \
  --repo . \
  --candidate "Dev-Flow architecture rehab: choose one Graphify-backed Ponytail slice, use subagents only where useful, run focused tests, write scorecard evidence, and stop after one safe slice" \
  --worker codex55 \
  --max-iterations 1 \
  --dry-run
```

Expected command contains:

```text
--profile dfcodex55 --judge-profile dfcodex55
```

Expected JSON properties:

```json
{
  "worker": "codex55",
  "profile": "dfcodex55",
  "judge_profile": "dfcodex55",
  "goal_template": "rehab",
  "started": false,
  "dry_run": true
}
```

- [ ] **Step 2: Inspect the generated goal file**

Run:

```bash
python - <<'PY'
import json
import subprocess
from pathlib import Path

cmd = [
    "/Users/josh/Desktop/Dev-Flow/.venv/bin/python",
    "/Users/josh/Desktop/Dev-Flow/skills/improve-codebase-architecture/scripts/start_rehab_loop.py",
    "--repo", "/Users/josh/Desktop/Dev-Flow",
    "--candidate", "Dev-Flow architecture rehab: choose one Graphify-backed Ponytail slice, use subagents only where useful, run focused tests, write scorecard evidence, and stop after one safe slice",
    "--worker", "codex55",
    "--max-iterations", "1",
    "--dry-run",
]
result = subprocess.run(cmd, cwd="/Users/josh/Desktop/Dev-Flow", text=True, capture_output=True, check=True)
payload = json.loads(result.stdout)
goal = Path(payload["goal_file"])
print(goal)
print(goal.read_text(encoding="utf-8"))
PY
```

Expected goal text includes:

```text
Work on one safe architecture slice only.
Do not commit generated graphify-out/ files.
Do not push, publish, open PRs, promote, or merge.
Write a markdown handoff with Status, Outcome, Files Changed, Verification, Risks, Recommended Next Steps, and Next Safe Action.
```

- [ ] **Step 3: Stop for operator approval before real Phase 2**

Do not run the non-dry-run Phase 2 command until the operator explicitly approves it after reviewing the dry-run command and goal file.

---

### Task 9: Approved Phase 2 Real Run

**Files:**
- Real Dev-Flow repo: `/Users/josh/Desktop/Dev-Flow`
- Generated goal under: `/Users/josh/Desktop/Dev-Flow/.devflow/architecture-rehab/goals/`
- Loop logs under: `/Users/josh/.hermes/logs/`
- Loop handoff under: `/Users/josh/.hermes/sessions/`
- Generated Graphify output must not be committed: `/Users/josh/Desktop/Dev-Flow/graphify-out/`

- [ ] **Step 1: Confirm approval in the current conversation**

Required operator approval text must clearly authorize the real Codex worker run. If approval is absent or ambiguous, ask for approval with the exact command that will run.

- [ ] **Step 2: Start the approved real run**

Run only after approval:

```bash
cd /Users/josh/Desktop/Dev-Flow
.venv/bin/python skills/improve-codebase-architecture/scripts/start_rehab_loop.py \
  --repo . \
  --candidate "Dev-Flow architecture rehab: choose one Graphify-backed Ponytail slice, use subagents only where useful, run focused tests, write scorecard evidence, and stop after one safe slice" \
  --worker codex55 \
  --max-iterations 1
```

Expected command behavior:

```text
--profile dfcodex55
--judge-profile dfcodex55
--max-iterations 1
```

Forbidden behavior:

```text
git push
pull request
promote
merge
generated graphify-out committed
more than one architecture slice
```

- [ ] **Step 3: Watch status during the run**

Run:

```bash
/Users/josh/Desktop/Loop\ Goal\ Script/loop.py status
```

After the slug is known, run:

```bash
cd /Users/josh/Desktop/Dev-Flow
.venv/bin/python skills/improve-codebase-architecture/scripts/rehab_loop_status.py \
  --repo . \
  --slug <loop_slug_from_start_rehab_loop_json>
```

Expected: status output remains parseable and shows at most one iteration.

- [ ] **Step 4: Inspect final diff before any follow-up loop**

Run:

```bash
cd /Users/josh/Desktop/Dev-Flow
git status --short
git diff --stat
git diff --check
```

Expected:

```text
git diff --check
```

exits 0. `git status --short` must not show staged or committed generated `graphify-out/` files.

- [ ] **Step 5: Verify focused tests named in the handoff**

Run the exact focused test commands named in the worker handoff. If the handoff names no focused tests, treat the run as incomplete and do not proceed to another loop.

- [ ] **Step 6: Confirm no orphans**

Run:

```bash
ps -axo pid,ppid,pgid,etime,command | grep -E '(/Users/josh/Desktop/Loop Goal Script/loop.py start|hermes -p dflocalfast|hermes -p dfcodex55)' | grep -v grep || true
```

Expected: no output.

---

## Final Report Template For The Next Agent

Use this format in the final response:

```markdown
## Status
<complete, blocked, or approval-gated>

## Outcome
<what ran and what it proved>

## Files Changed
<absolute paths, or "(none)">

## Verification
<commands and pass/fail results>

## Risks
<remaining risk, including model/endpoint issues or uninspected diffs>

## Recommended Next Steps
<only concrete next steps>

## Next Safe Action
<one command or approval request>
```

## Self-Review

- Spec coverage: The plan covers Phase 1 smoke setup, smoke execution, status/watch/control visibility, no-orphan checks, Codex judge defaults for local-fast and codex55 rehab dry-runs, the Phase 2 approval gate, and real-run hard gates.
- Placeholder scan: No forbidden placeholder markers or vague test instructions remain. Conditional branches include exact commands.
- Type and command consistency: Worker profiles are consistently `dflocalfast` and `dfcodex55`; judge profile is consistently `dfcodex55`; smoke uses `--no-judge`; rehab uses `--judge-profile dfcodex55`.
