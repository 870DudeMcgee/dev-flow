# Graphify Ponytail Rehab Program Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden the planner-worker-judge rehab loop, then create a Graphify/Ponytail candidate queue that subagents can work through in small verified chunks.

**Architecture:** Start with the foundation lane in Loop Goal Script so invalid planner output cannot spawn workers. Add an explicit planner toolset override so the planner can avoid broken profile defaults without changing worker toolsets. Then create a local candidate queue and read-only subagent scout/reviewer packets; implementation workers remain serialized by file ownership.

**Tech Stack:** Python 3, pytest, Hermes profiles/toolsets, Loop Goal Script, Dev-Flow architecture rehab skill scripts, Graphify scorecards, Markdown candidate packets.

---

## Current State To Preserve

- Dev-Flow repo: `/Users/josh/Desktop/Dev-Flow`
- Loop Goal Script repo: `/Users/josh/Desktop/Loop Goal Script`
- The Dev-Flow worktree is already dirty with architecture-skill changes; do not revert them.
- The Loop Goal Script worktree is already dirty with planner-worker-judge changes and a partial planner validation patch; do not revert them.
- Do not push, publish, open PRs, promote, merge, cleanup, or commit unless the operator explicitly asks.
- Do not commit generated `graphify-out/` files.
- Do not use `/Users/jewelbait/Desktop/DevFlow`.

## File Responsibilities

- `/Users/josh/Desktop/Loop Goal Script/loop.py`: loop runtime, planner request, worker spawn gate, foreground/background CLI args.
- `/Users/josh/Desktop/Loop Goal Script/test_structured_handoff.py`: unit tests for planner prompt, command construction, and planner output validation.
- `/Users/josh/Desktop/Loop Goal Script/test_task_store_sync.py`: run-loop behavior tests, including planner-before-worker and planner-blocked gates.
- `/Users/josh/Desktop/Loop Goal Script/test_cli.py`: background launch CLI argument propagation tests.
- `/Users/josh/Desktop/Dev-Flow/skills/improve-codebase-architecture/scripts/start_rehab_loop.py`: wrapper that builds rehab goals and Loop Goal Script commands.
- `/Users/josh/Desktop/Dev-Flow/tests/test_architecture_rehab_skill_scripts.py`: wrapper command regression tests.
- `/Users/josh/Desktop/Dev-Flow/.devflow/architecture-rehab/work-queue.md`: local ignored candidate queue for Graphify/Ponytail rehab packets.

---

### Task 1: Lock The Planner Output Contract

**Files:**
- Modify: `/Users/josh/Desktop/Loop Goal Script/loop.py`
- Modify: `/Users/josh/Desktop/Loop Goal Script/test_structured_handoff.py`

- [ ] **Step 1: Ensure the valid planner fixture has all required headings**

In `/Users/josh/Desktop/Loop Goal Script/test_structured_handoff.py`, make `test_request_worker_plan_uses_planner_profile_and_graphify_ponytail_prompt` use this stdout fixture:

```python
    completed.stdout = """# Worker Plan
## Codebase Refactor Direction
Use the smallest dogfood slice in the broader roadmap.
## Current Small Fix
Move one repeated dogfood task mechanics path into the recorder.
## Files
- src/devflow/control_room/dogfood.py
## Steps
1. Add the focused recorder helper.
## Tests
- pytest tests/test_dogfood_harness.py -q
## Stop Conditions
- Stop if graph evidence is stale.
"""
```

Expected assertion shape:

```python
    assert plan.startswith("# Worker Plan")
    assert "## Current Small Fix" in plan
```

- [ ] **Step 2: Add the warning-output regression test**

Add this test in `/Users/josh/Desktop/Loop Goal Script/test_structured_handoff.py` immediately after `test_request_worker_plan_uses_planner_profile_and_graphify_ponytail_prompt`:

```python
def test_request_worker_plan_rejects_stdout_without_required_plan_headings():
    """Planner warnings on stdout are not worker plans and must not spawn workers."""
    completed = MagicMock()
    completed.stdout = "Warning: Unknown toolsets: devflow, messaging, moa\n"
    completed.stderr = ""
    completed.returncode = 0

    with patch("loop.subprocess.run", return_value=completed):
        plan = request_worker_plan(
            "Tighten Dogfood harness mechanics",
            {"completed": "none", "remaining": "Build it", "active_state": "clean", "blockers": "none", "next_action": "Start"},
            planner_profile="dfplanner",
            workdir="/repo",
        )

    assert plan == ""
```

- [ ] **Step 3: Run the regression red check**

Run:

```bash
cd /Users/josh/Desktop/Loop\ Goal\ Script
/Users/josh/Desktop/Dev-Flow/.venv/bin/python -m pytest \
  test_structured_handoff.py::test_request_worker_plan_rejects_stdout_without_required_plan_headings \
  -q
```

Expected before the runtime fix:

```text
FAILED test_structured_handoff.py::test_request_worker_plan_rejects_stdout_without_required_plan_headings
```

If the current worktree already passes because the interrupted run applied this patch, record that and continue to Step 5.

- [ ] **Step 4: Add the minimal runtime validation**

In `/Users/josh/Desktop/Loop Goal Script/loop.py`, add this constant near the existing loop constants:

```python
REQUIRED_WORKER_PLAN_HEADINGS = (
    "# Worker Plan",
    "## Codebase Refactor Direction",
    "## Current Small Fix",
    "## Files",
    "## Steps",
    "## Tests",
    "## Stop Conditions",
)
```

Then update `request_worker_plan` after `plan = (result.stdout or "").strip()`:

```python
    if result.returncode != 0 or not plan:
        return ""
    if not all(heading in plan for heading in REQUIRED_WORKER_PLAN_HEADINGS):
        logging.warning("Planner output missing required worker plan headings; refusing to spawn worker")
        return ""
    return plan
```

- [ ] **Step 5: Run the green check**

Run:

```bash
cd /Users/josh/Desktop/Loop\ Goal\ Script
/Users/josh/Desktop/Dev-Flow/.venv/bin/python -m pytest \
  test_structured_handoff.py::test_request_worker_plan_rejects_stdout_without_required_plan_headings \
  test_structured_handoff.py::test_request_worker_plan_uses_planner_profile_and_graphify_ponytail_prompt \
  -q
```

Expected:

```text
2 passed
```

---

### Task 2: Prove Planner-Blocked Prevents Worker Spawn

**Files:**
- Modify: `/Users/josh/Desktop/Loop Goal Script/test_task_store_sync.py`

- [ ] **Step 1: Add the run-loop blocked regression**

Add this test after `test_run_loop_sends_planner_plan_to_worker_before_spawn` in `/Users/josh/Desktop/Loop Goal Script/test_task_store_sync.py`:

```python
def test_run_loop_blocks_before_worker_when_planner_returns_no_plan(env):
    """A missing or invalid planner plan must stop the loop before worker spawn."""
    import loop

    goal_text = "# Task task-planner\nTighten Dogfood harness mechanics"
    events = []
    originals = {
        "request_worker_plan": loop.request_worker_plan,
        "save_worker_plan": loop.save_worker_plan,
        "spawn_session": loop.spawn_session,
        "monitor_session": loop.monitor_session,
        "save_handoff": loop.save_handoff,
        "shutdown": loop._shutdown,
    }

    def fake_request_worker_plan(goal, handoff, *, planner_profile=None, judge_profile=None, workdir="", timeout=loop.JUDGE_PLAN_TIMEOUT, planner_toolsets=None):
        events.append(("planner", planner_profile or judge_profile, workdir, planner_toolsets))
        return ""

    def fake_save_handoff(goal, **kwargs):
        events.append(
            (
                "handoff",
                kwargs.get("session_id"),
                kwargs.get("blockers"),
                kwargs.get("next_action"),
            )
        )

    def fail_spawn(*args, **kwargs):
        raise AssertionError("worker should not spawn without a valid planner plan")

    def fail_monitor(*args, **kwargs):
        raise AssertionError("worker monitor should not run without a valid planner plan")

    try:
        loop.request_worker_plan = fake_request_worker_plan
        loop.save_worker_plan = lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("invalid planner output must not be saved as a worker plan"))
        loop.spawn_session = fail_spawn
        loop.monitor_session = fail_monitor
        loop.save_handoff = fake_save_handoff
        loop._shutdown = False

        rc = loop.run_loop(
            goal_text,
            max_iterations=1,
            no_judge=False,
            judge_profile="dfcodex55",
            planner_profile="dfplanner",
            profile="worker-profile",
            workdir="/repo",
        )
    finally:
        for name, value in originals.items():
            setattr(loop, name, value)

    assert rc == 0
    assert events == [
        ("planner", "dfplanner", "/repo", None),
        (
            "handoff",
            "planner-blocked",
            "planner profile dfplanner returned no worker plan",
            "Fix planner/profile output; do not start worker without a plan.",
        ),
    ]
```

- [ ] **Step 2: Run the new test**

Run:

```bash
cd /Users/josh/Desktop/Loop\ Goal\ Script
/Users/josh/Desktop/Dev-Flow/.venv/bin/python -m pytest \
  test_task_store_sync.py::test_run_loop_blocks_before_worker_when_planner_returns_no_plan \
  -q
```

Expected:

```text
1 passed
```

---

### Task 3: Add Explicit Planner Toolsets To Loop Goal Script

**Files:**
- Modify: `/Users/josh/Desktop/Loop Goal Script/loop.py`
- Modify: `/Users/josh/Desktop/Loop Goal Script/test_structured_handoff.py`
- Modify: `/Users/josh/Desktop/Loop Goal Script/test_task_store_sync.py`
- Modify: `/Users/josh/Desktop/Loop Goal Script/test_cli.py`

- [ ] **Step 1: Add a planner toolset command test**

Add this test in `/Users/josh/Desktop/Loop Goal Script/test_structured_handoff.py` after the warning-output regression:

```python
def test_request_worker_plan_passes_planner_toolsets_to_hermes():
    """Planner toolsets override broken profile defaults without changing worker toolsets."""
    completed = MagicMock()
    completed.stdout = """# Worker Plan
## Codebase Refactor Direction
Keep the rehab roadmap broad but implementation tiny.
## Current Small Fix
Fix one planner gate.
## Files
- loop.py
## Steps
1. Update planner invocation.
## Tests
- pytest test_structured_handoff.py -q
## Stop Conditions
- Stop if planner stdout is not Markdown.
"""
    completed.stderr = ""
    completed.returncode = 0

    with patch("loop.subprocess.run", return_value=completed) as mock_run:
        plan = request_worker_plan(
            "Tighten Dogfood harness mechanics",
            {"completed": "none", "remaining": "Build it", "active_state": "clean", "blockers": "none", "next_action": "Start"},
            planner_profile="dfplanner",
            workdir="/repo",
            planner_toolsets="hermes-cli",
        )

    cmd = mock_run.call_args.args[0]
    assert plan.startswith("# Worker Plan")
    assert "-t" in cmd
    assert cmd[cmd.index("-t") + 1] == "hermes-cli"
```

- [ ] **Step 2: Run the planner toolset test red check**

Run:

```bash
cd /Users/josh/Desktop/Loop\ Goal\ Script
/Users/josh/Desktop/Dev-Flow/.venv/bin/python -m pytest \
  test_structured_handoff.py::test_request_worker_plan_passes_planner_toolsets_to_hermes \
  -q
```

Expected before implementation:

```text
FAILED
```

- [ ] **Step 3: Add `planner_toolsets` to `request_worker_plan`**

In `/Users/josh/Desktop/Loop Goal Script/loop.py`, update the signature:

```python
def request_worker_plan(
    goal_text: str,
    handoff: dict,
    *,
    planner_profile: str | None = None,
    judge_profile: str | None = None,
    workdir: str = "",
    timeout: int = JUDGE_PLAN_TIMEOUT,
    planner_toolsets: str | None = None,
) -> str:
```

Replace the hard-coded subprocess command with:

```python
    cmd = build_hermes_chat_command(profile, prompt, hermes_toolsets=planner_toolsets)
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
        cwd=workdir or None,
        env=env,
    )
```

- [ ] **Step 4: Thread `planner_toolsets` through `run_loop`**

Update the `run_loop` signature in `/Users/josh/Desktop/Loop Goal Script/loop.py`:

```python
def run_loop(goal_text: str, *, profile: str = DEFAULT_PROFILE,
             max_iterations: int = DEFAULT_MAX_ITERATIONS,
             no_judge: bool = False, debug: bool = False,
             judge_profile: str | None = None,
             planner_profile: str | None = None,
             planner_toolsets: str | None = None,
             workdir: str = "", stall_timeout: int = DEFAULT_STALL_TIMEOUT,
             max_no_progress: int = DEFAULT_MAX_NO_PROGRESS,
             session_timeout: int = SESSION_TIMEOUT,
             hermes_max_turns: int | None = None,
             hermes_toolsets: str | None = None,
             hermes_ignore_rules: bool = False) -> int:
```

Update the planner call inside `run_loop`:

```python
            worker_plan = request_worker_plan(
                goal_text,
                handoff,
                planner_profile=effective_planner_profile,
                workdir=workdir,
                planner_toolsets=planner_toolsets,
            )
```

- [ ] **Step 5: Update existing fake planner tests for the new keyword**

In `/Users/josh/Desktop/Loop Goal Script/test_task_store_sync.py`, update existing fake planner signatures to accept `planner_toolsets=None`.

For `test_run_loop_sends_planner_plan_to_worker_before_spawn`, use:

```python
    def fake_request_worker_plan(goal, handoff, *, planner_profile=None, judge_profile=None, workdir="", timeout=loop.JUDGE_PLAN_TIMEOUT, planner_toolsets=None):
        events.append(("planner", planner_profile or judge_profile, workdir, planner_toolsets))
        return "# Worker Plan\n## Codebase Refactor Direction\nDogfood cleanup.\n## Current Small Fix\nEdit one recorder helper and one test.\n## Files\n- src/devflow/control_room/dogfood.py\n## Steps\n1. Edit one call site.\n## Tests\n- pytest tests/test_dogfood_harness.py -q\n## Stop Conditions\n- Stop if graph is stale."
```

Update the expected first event:

```python
        ("planner", "dfplanner", "/repo", None),
```

- [ ] **Step 6: Add a `run_loop` planner toolset pass-through test**

Add this test after the planner-before-worker test:

```python
def test_run_loop_passes_planner_toolsets_to_worker_plan_request(env):
    """Planner toolsets are independent from worker toolsets."""
    import loop

    goal_text = "# Task task-planner\nTighten Dogfood harness mechanics"
    events = []
    originals = {
        "request_worker_plan": loop.request_worker_plan,
        "save_worker_plan": loop.save_worker_plan,
        "spawn_session": loop.spawn_session,
        "monitor_session": loop.monitor_session,
        "extract_handoff": loop.extract_handoff,
        "has_progress": loop.has_progress,
        "judge_goal": loop.judge_goal,
        "shutdown": loop._shutdown,
    }

    def fake_request_worker_plan(goal, handoff, *, planner_profile=None, judge_profile=None, workdir="", timeout=loop.JUDGE_PLAN_TIMEOUT, planner_toolsets=None):
        events.append(("planner", planner_profile or judge_profile, workdir, planner_toolsets))
        return "# Worker Plan\n## Codebase Refactor Direction\nDogfood cleanup.\n## Current Small Fix\nEdit one recorder helper and one test.\n## Files\n- src/devflow/control_room/dogfood.py\n## Steps\n1. Edit one call site.\n## Tests\n- pytest tests/test_dogfood_harness.py -q\n## Stop Conditions\n- Stop if graph is stale."

    def fake_spawn_session(*args, **kwargs):
        events.append(("spawn", kwargs.get("hermes_toolsets"), kwargs.get("worker_plan", "").startswith("# Worker Plan")))
        return object()

    try:
        loop.request_worker_plan = fake_request_worker_plan
        loop.save_worker_plan = lambda goal, iteration, plan: events.append(("save_plan", iteration)) or loop.SESSIONS / "worker-plan.md"
        loop.spawn_session = fake_spawn_session
        loop.monitor_session = lambda *args, **kwargs: ("handoff output", 0, False)
        loop.extract_handoff = lambda output, goal: {
            "completed": "implemented slice",
            "remaining": "Review",
            "active_state": "tests",
            "blockers": "",
            "next_action": "Verify",
        }
        loop.has_progress = lambda prev, new: True
        loop.judge_goal = lambda goal, handoff_text, debug=False, judge_profile=None: {
            "done": True,
            "blocked": False,
            "reason": "all checks passed",
        }
        loop._shutdown = False

        rc = loop.run_loop(
            goal_text,
            max_iterations=1,
            no_judge=False,
            judge_profile="dfcodex55",
            planner_profile="dfplanner",
            planner_toolsets="hermes-cli",
            profile="worker-profile",
            workdir="/repo",
            hermes_toolsets="terminal",
        )
    finally:
        for name, value in originals.items():
            setattr(loop, name, value)

    assert rc == 0
    assert events[:3] == [
        ("planner", "dfplanner", "/repo", "hermes-cli"),
        ("save_plan", 1),
        ("spawn", "terminal", True),
    ]
```

- [ ] **Step 7: Add background launch propagation**

Update `launch_background` in `/Users/josh/Desktop/Loop Goal Script/loop.py`:

```python
def launch_background(goal_text: str, *, profile: str = DEFAULT_PROFILE,
                      max_iterations: int = DEFAULT_MAX_ITERATIONS,
                      no_judge: bool = False, judge_profile: str | None = None,
                      planner_profile: str | None = None,
                      planner_toolsets: str | None = None,
                      workdir: str = "",
                      stall_timeout: int = DEFAULT_STALL_TIMEOUT,
                      max_no_progress: int = DEFAULT_MAX_NO_PROGRESS,
                      session_timeout: int = SESSION_TIMEOUT,
                      hermes_max_turns: int | None = None,
                      hermes_toolsets: str | None = None,
                      hermes_ignore_rules: bool = False) -> int:
```

Add the command extension:

```python
    if planner_toolsets:
        cmd.extend(["--planner-toolsets", planner_toolsets])
```

Add this test to `/Users/josh/Desktop/Loop Goal Script/test_cli.py` after `test_launch_background_includes_planner_profile`:

```python
def test_launch_background_includes_planner_toolsets():
    with patch("loop.subprocess.Popen") as mock_popen, \
         patch("loop.LOGS", MagicMock(__truediv__=MagicMock(return_value=Path("/tmp/test.log")))), \
         patch("builtins.open", MagicMock(__enter__=MagicMock(), __exit__=MagicMock())), \
         patch("loop.Path") as mock_path:
        mock_popen.return_value = MagicMock(pid=999)
        mock_path.return_value = Path("/tmp/test.log")
        launch_background("Goal", planner_toolsets="hermes-cli")
        cmd = mock_popen.call_args[0][0]
        assert "--planner-toolsets" in cmd
        assert "hermes-cli" in cmd
```

- [ ] **Step 8: Add CLI arguments and pass-throughs**

In `/Users/josh/Desktop/Loop Goal Script/loop.py`, add parser args near each existing `--planner-profile`:

```python
    parser.add_argument("--planner-toolsets", default=None, help="Hermes toolsets to use for pre-worker planning calls")
```

```python
    p_start.add_argument("--planner-toolsets", default=None, help="Hermes toolsets to use for pre-worker planning calls")
```

```python
    p_resume.add_argument("--planner-toolsets", default=None, help="Hermes toolsets to use for pre-worker planning calls")
```

Pass `planner_toolsets=getattr(args, "planner_toolsets", None)` into every `run_loop` and `launch_background` call that already passes `planner_profile`.

- [ ] **Step 9: Run Loop Goal Script focused tests**

Run:

```bash
cd /Users/josh/Desktop/Loop\ Goal\ Script
/Users/josh/Desktop/Dev-Flow/.venv/bin/python -m pytest \
  test_structured_handoff.py::test_request_worker_plan_uses_planner_profile_and_graphify_ponytail_prompt \
  test_structured_handoff.py::test_request_worker_plan_rejects_stdout_without_required_plan_headings \
  test_structured_handoff.py::test_request_worker_plan_passes_planner_toolsets_to_hermes \
  test_task_store_sync.py::test_run_loop_sends_planner_plan_to_worker_before_spawn \
  test_task_store_sync.py::test_run_loop_blocks_before_worker_when_planner_returns_no_plan \
  test_task_store_sync.py::test_run_loop_passes_planner_toolsets_to_worker_plan_request \
  test_cli.py::test_launch_background_includes_planner_profile \
  test_cli.py::test_launch_background_includes_planner_toolsets \
  -q
```

Expected:

```text
8 passed
```

---

### Task 4: Add Planner Toolsets To The Dev-Flow Wrapper

**Files:**
- Modify: `/Users/josh/Desktop/Dev-Flow/skills/improve-codebase-architecture/scripts/start_rehab_loop.py`
- Modify: `/Users/josh/Desktop/Dev-Flow/tests/test_architecture_rehab_skill_scripts.py`

- [ ] **Step 1: Add a wrapper command regression**

Add this test to `/Users/josh/Desktop/Dev-Flow/tests/test_architecture_rehab_skill_scripts.py` after `test_start_rehab_loop_codex_worker_uses_codex55_profile`:

```python
def test_start_rehab_loop_passes_planner_toolsets(tmp_path: Path) -> None:
    start = _load_script("start_rehab_loop.py")
    repo = tmp_path / "repo"
    repo.mkdir()
    loop_script = tmp_path / "Loop Goal Script" / "loop.py"
    loop_script.parent.mkdir()
    loop_script.write_text("#!/usr/bin/env python3\n", encoding="utf-8")

    result = start.prepare_rehab_loop(
        repo,
        candidate="Use explicit planner toolsets",
        loop_script=loop_script,
        goal_dir=tmp_path / "goals",
        worker="codex55",
        planner_toolsets="hermes-cli",
        dry_run=True,
        timestamp="20260628T200000Z",
    )

    assert "--planner-toolsets" in result["command"]
    assert result["command"][result["command"].index("--planner-toolsets") + 1] == "hermes-cli"
    assert result["planner_toolsets"] == "hermes-cli"
```

- [ ] **Step 2: Run the wrapper regression red check**

Run:

```bash
cd /Users/josh/Desktop/Dev-Flow
.venv/bin/python -m pytest \
  tests/test_architecture_rehab_skill_scripts.py::test_start_rehab_loop_passes_planner_toolsets \
  -q
```

Expected before implementation:

```text
FAILED
```

- [ ] **Step 3: Thread `planner_toolsets` through `_command` and `prepare_rehab_loop`**

In `/Users/josh/Desktop/Dev-Flow/skills/improve-codebase-architecture/scripts/start_rehab_loop.py`, update `_command`:

```python
def _command(
    loop_script: Path,
    goal_file: Path,
    repo: Path,
    max_iterations: int,
    background: bool,
    profile: str,
    *,
    no_judge: bool = False,
    judge_profile: str | None = None,
    planner_profile: str | None = None,
    planner_toolsets: str | None = None,
    stall_timeout: int | None = None,
    session_timeout: int | None = None,
    hermes_max_turns: int | None = None,
    hermes_toolsets: str | None = None,
    hermes_ignore_rules: bool = False,
) -> list[str]:
```

Add this after planner profile handling:

```python
    if not no_judge and planner_toolsets:
        command.extend(["--planner-toolsets", planner_toolsets])
```

Update `prepare_rehab_loop` signature:

```python
    planner_toolsets: str | None = None,
```

Pass it into `_command`:

```python
        planner_toolsets=planner_toolsets,
```

Add it to the result payload:

```python
        "planner_toolsets": planner_toolsets,
```

- [ ] **Step 4: Add CLI argument and pass-through**

In `main`, add:

```python
    parser.add_argument(
        "--planner-toolsets",
        default=None,
        help="Hermes toolsets used for Loop-Goal-Script planner calls.",
    )
```

Pass it into `prepare_rehab_loop`:

```python
        planner_toolsets=args.planner_toolsets,
```

- [ ] **Step 5: Run wrapper tests**

Run:

```bash
cd /Users/josh/Desktop/Dev-Flow
.venv/bin/python -m pytest tests/test_architecture_rehab_skill_scripts.py -q
```

Expected:

```text
11 passed
```

---

### Task 5: Create The Local Rehab Candidate Queue

**Files:**
- Create: `/Users/josh/Desktop/Dev-Flow/.devflow/architecture-rehab/work-queue.md`

- [ ] **Step 1: Add the queue file**

Create `/Users/josh/Desktop/Dev-Flow/.devflow/architecture-rehab/work-queue.md` with this content:

```markdown
# Graphify Ponytail Rehab Work Queue

This local queue is ignored by git. It captures unlimited architecture rehab
ideas while keeping active implementation constrained.

## Queue Rules

- Ready packets need Graphify evidence and source evidence.
- Graph scouts and Ponytail reviewers may run in parallel.
- Implementation workers must use isolated worktrees or serialize by file set.
- Do not run two implementation workers that touch the same source or test file.
- Generated `graphify-out/` files are evidence and must stay uncommitted.
- No push, PR, promotion, merge, cleanup, or publish without explicit approval.

## Candidate: Planner Contract Foundation

Recommendation: Strong

Module goal:
Make Loop Goal Script block before worker spawn unless the planner artifact is a
real worker plan.

Graphify evidence:
- Report commit: not required; this is a loop safety bug observed during live run.
- Scorecard: not required for foundation safety slice.
- Node IDs: n/a.
- Hotspot/delta: planner output accepted as worker guidance without structural validation.
- Diagnostics: `/Users/josh/.hermes/sessions/worker-plan-graphify-ponytail-architecture-rehab-goal-repository--c615a9-iter-1.md`.

Source evidence:
- `/Users/josh/Desktop/Loop Goal Script/loop.py`: `request_worker_plan` returns non-empty stdout as a plan unless validated.
- `/Users/josh/Desktop/Loop Goal Script/test_structured_handoff.py`: needs warning-output regression.
- `/Users/josh/Desktop/Loop Goal Script/test_task_store_sync.py`: needs loop-level no-worker-spawn regression.

Ponytail gate:
- Existing code reused/deleted: reuse `build_hermes_chat_command`; add one shared validation gate.
- Deletion test: without the gate, warning-only stdout can spawn workers.
- Seam test: no new interface or adapter.
- Slice size: one runtime guard plus tests.

Implementation slice:
1. Validate required worker plan headings.
2. Add planner-blocked run-loop test.
3. Add explicit planner toolsets.

Conflict map:
- Files touched: `/Users/josh/Desktop/Loop Goal Script/loop.py`, `/Users/josh/Desktop/Loop Goal Script/test_structured_handoff.py`, `/Users/josh/Desktop/Loop Goal Script/test_task_store_sync.py`, `/Users/josh/Desktop/Loop Goal Script/test_cli.py`, `/Users/josh/Desktop/Dev-Flow/skills/improve-codebase-architecture/scripts/start_rehab_loop.py`, `/Users/josh/Desktop/Dev-Flow/tests/test_architecture_rehab_skill_scripts.py`.
- Cannot run in parallel with: any Loop Goal Script runtime or Dev-Flow rehab wrapper edit.

Verification:
```bash
cd /Users/josh/Desktop/Loop\ Goal\ Script
/Users/josh/Desktop/Dev-Flow/.venv/bin/python -m pytest test_structured_handoff.py test_task_store_sync.py test_cli.py -q
cd /Users/josh/Desktop/Dev-Flow
.venv/bin/python -m pytest tests/test_architecture_rehab_skill_scripts.py -q
```

Risks:
- Hermes profile config may still contain stale toolsets; the loop must surface that as planner-blocked instead of spawning a worker.

Next safe action:
Finish the foundation implementation plan tasks before dispatching app-code workers.

## Candidate: Dogfood Harness Recorder Concentration

Recommendation: Worth exploring

Module goal:
Concentrate repeated dogfood task/result mechanics behind `CaseResultRecorder`
without changing case IDs, report schema, scoring, promotion behavior, or CLI behavior.

Graphify evidence:
- Report commit: `9fb51f5b` from current scorecards.
- Scorecard: `/Users/josh/Desktop/Dev-Flow/.devflow/architecture-rehab/scorecards/before-20260628T183217Z.json`.
- Node IDs: scout must fill from `graphify-out/graph.json`.
- Hotspot/delta: dogfood harness table/callflow screenshots already exist under `.devflow/architecture-rehab/screenshots/`.
- Diagnostics: scout must verify graph freshness before implementation.

Source evidence:
- `/Users/josh/Desktop/Dev-Flow/src/devflow/control_room/dogfood.py`: scout must identify one repeated mechanics pattern.
- `/Users/josh/Desktop/Dev-Flow/src/devflow/control_room/dogfood_case_result.py`: scout must verify existing recorder behavior.
- `/Users/josh/Desktop/Dev-Flow/tests/test_dogfood_harness.py`: focused coverage target.

Ponytail gate:
- Existing code reused/deleted: reuse `CaseResultRecorder`; do not add a new module.
- Deletion test: replacing one repeated call-site mechanics block should reduce caller-specific command recording.
- Seam test: no new adapter; recorder already exists.
- Slice size: one dogfood case or one repeated mechanics path only.

Implementation slice:
1. Scout exact repeated pattern.
2. Write one failing `tests/test_dogfood_harness.py` test.
3. Move one mechanics path into recorder and rerun focused tests.

Conflict map:
- Files touched: `src/devflow/control_room/dogfood.py`, `src/devflow/control_room/dogfood_case_result.py`, `tests/test_dogfood_harness.py`.
- Cannot run in parallel with: any dogfood harness implementation slice.

Verification:
```bash
cd /Users/josh/Desktop/Dev-Flow
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_dogfood_harness.py -q
python skills/improve-codebase-architecture/scripts/graphify_rehab_score.py --repo . --baseline .devflow/architecture-rehab/scorecards/before-20260628T183217Z.json --output .devflow/architecture-rehab/scorecards/after-dogfood-harness.json
```

Risks:
- Dogfood report semantics are product-facing evidence; preserve output shape.

Next safe action:
Dispatch a read-only graph scout after the foundation slice is verified.
```

- [ ] **Step 2: Verify the local queue remains ignored**

Run:

```bash
cd /Users/josh/Desktop/Dev-Flow
git check-ignore -v .devflow/architecture-rehab/work-queue.md
```

Expected:

```text
.gitignore:8:.devflow/	.devflow/architecture-rehab/work-queue.md
```

---

### Task 6: Dispatch Read-Only Scout And Ponytail Review Subagents

**Files:**
- Read only: `/Users/josh/Desktop/Dev-Flow/graphify-out/GRAPH_REPORT.md`
- Read only: `/Users/josh/Desktop/Dev-Flow/graphify-out/graph.json`
- Read only: `/Users/josh/Desktop/Dev-Flow/src/devflow/control_room/`
- Read only: `/Users/josh/Desktop/Dev-Flow/tests/`
- Modify only by coordinator after review: `/Users/josh/Desktop/Dev-Flow/.devflow/architecture-rehab/work-queue.md`

- [ ] **Step 1: Dispatch Graph Scout A for dogfood mechanics**

Use a read-only subagent with this prompt:

```text
You are Graph Scout A for Dev-Flow Graphify/Ponytail rehab.

Repository: /Users/josh/Desktop/Dev-Flow
Read only. Do not edit files.

Goal:
Inspect graphify-out/GRAPH_REPORT.md, graphify-out/graph.json,
src/devflow/control_room/dogfood.py,
src/devflow/control_room/dogfood_case_result.py, and tests/test_dogfood_harness.py.

Find exactly one small dogfood harness mechanics concentration candidate around
CaseResultRecorder. Return a candidate packet with:
- Graphify evidence: report commit, scorecard path, node IDs or source-file graph evidence, freshness status.
- Source evidence: exact repeated mechanics pattern and exact test surface.
- Ponytail gate: existing code reused/deleted, deletion test, seam test, slice size.
- Conflict map: files touched and files that block parallel work.
- Verification: one focused pytest command and one after-scorecard command.

Hard stops:
- Do not propose a new module.
- Do not propose broad dogfood cleanup.
- Do not edit files.
- If graph evidence is stale, report stale and stop.
```

- [ ] **Step 2: Dispatch Graph Scout B for high-degree control-room hotspots**

Use a read-only subagent with this prompt:

```text
You are Graph Scout B for Dev-Flow Graphify/Ponytail rehab.

Repository: /Users/josh/Desktop/Dev-Flow
Read only. Do not edit files.

Goal:
Inspect graphify-out/GRAPH_REPORT.md, graphify-out/graph.json, and
src/devflow/control_room/. Find up to three high-degree control-room candidates
where a small slice can delete, reuse, or concentrate complexity.

Return only candidate packets. Each packet must include Graphify evidence,
source evidence, Ponytail gate, conflict map, verification command, risk, and
next safe action.

Hard stops:
- No framework, manager, registry, orchestrator, or one-adapter seam proposals.
- No implementation.
- If a candidate needs product direction, mark it speculative.
```

- [ ] **Step 3: Dispatch Graph Scout C for task/log/evidence projection paths**

Use a read-only subagent with this prompt:

```text
You are Graph Scout C for Dev-Flow Graphify/Ponytail rehab.

Repository: /Users/josh/Desktop/Dev-Flow
Read only. Do not edit files.

Goal:
Inspect graphify-out evidence and the operating-layer code paths that project
tasks, logs, reports, and evidence into the UI. Find up to three candidates
where repeated projection mechanics can be concentrated without changing UI
behavior.

Return candidate packets with Graphify evidence, source evidence, Ponytail gate,
conflict map, verification command, risk, and next safe action.

Hard stops:
- Do not touch public UI behavior.
- Do not add a new adapter unless two real callers already need it.
- Do not edit files.
```

- [ ] **Step 4: Dispatch Ponytail Reviewer**

After scout outputs are available, use a read-only reviewer subagent with this prompt:

```text
You are the Ponytail reviewer for Dev-Flow Graphify/Ponytail rehab.

Review candidate packets from Graph Scout A, B, and C. Reject candidates that:
- add a new seam with one implementation
- rename without deleting or concentrating complexity
- require broad product decisions
- lack Graphify evidence or source evidence
- lack a focused test surface

Return:
1. Accepted candidates ordered by highest value.
2. Rejected candidates with one-line reasons.
3. File conflict groups so implementation workers can be serialized safely.

Read only. Do not edit files.
```

- [ ] **Step 5: Coordinator appends reviewed packets**

After reviewing subagent outputs manually, the coordinator appends only accepted packets to `/Users/josh/Desktop/Dev-Flow/.devflow/architecture-rehab/work-queue.md`.

Run:

```bash
cd /Users/josh/Desktop/Dev-Flow
git diff --check -- .devflow/architecture-rehab/work-queue.md
```

Expected:

```text
<no output>
```

---

### Task 7: Verify The Foundation And Dry-Run The Next Live Loop

**Files:**
- Read only: `/Users/josh/Desktop/Dev-Flow/.devflow/architecture-rehab/work-queue.md`
- Generated goal: `/Users/josh/Desktop/Dev-Flow/.devflow/architecture-rehab/goals/`

- [ ] **Step 1: Run focused Loop Goal Script suite**

Run:

```bash
cd /Users/josh/Desktop/Loop\ Goal\ Script
/Users/josh/Desktop/Dev-Flow/.venv/bin/python -m pytest \
  test_structured_handoff.py \
  test_task_store_sync.py \
  test_cli.py \
  -q
```

Expected:

```text
0 failed
```

- [ ] **Step 2: Run Dev-Flow wrapper suite**

Run:

```bash
cd /Users/josh/Desktop/Dev-Flow
.venv/bin/python -m pytest tests/test_architecture_rehab_skill_scripts.py -q
```

Expected:

```text
11 passed
```

- [ ] **Step 3: Run whitespace checks in both repos**

Run:

```bash
cd /Users/josh/Desktop/Loop\ Goal\ Script
git diff --check
cd /Users/josh/Desktop/Dev-Flow
git diff --check
```

Expected:

```text
<no output>
```

- [ ] **Step 4: Smoke the planner toolset override without a loop**

Run:

```bash
cd /Users/josh/Desktop/Dev-Flow
hermes -p dfcodex55 chat -q 'Return exactly: ok' -Q -t hermes-cli --max-turns 1
```

Expected output includes:

```text
ok
```

Expected output does not include:

```text
Warning: Unknown toolsets
```

- [ ] **Step 5: Dry-run the foundation-safe rehab command**

Run:

```bash
cd /Users/josh/Desktop/Dev-Flow
.venv/bin/python skills/improve-codebase-architecture/scripts/start_rehab_loop.py \
  --repo /Users/josh/Desktop/Dev-Flow \
  --candidate "Tighten Dogfood Harness Mechanics: choose one reviewed Graphify/Ponytail work-queue packet, implement only the current small fix, preserve public behavior, and stop after one test-backed slice." \
  --scorecard /Users/josh/Desktop/Dev-Flow/.devflow/architecture-rehab/scorecards/before-20260628T183217Z.json \
  --worker codex55 \
  --profile dfcodex55 \
  --planner-profile dfcodex55 \
  --planner-toolsets hermes-cli \
  --judge-profile dfcodex55 \
  --max-iterations 1 \
  --session-timeout 1800 \
  --stall-timeout 300 \
  --dry-run
```

Expected JSON properties:

```json
{
  "worker": "codex55",
  "profile": "dfcodex55",
  "planner_profile": "dfcodex55",
  "planner_toolsets": "hermes-cli",
  "judge_profile": "dfcodex55",
  "goal_template": "rehab",
  "started": false,
  "dry_run": true
}
```

Expected command contains:

```text
--planner-toolsets hermes-cli
```

- [ ] **Step 6: Stop for operator approval before real loop**

Do not start the real loop until the operator explicitly approves the dry-run command and candidate packet.

Real command after approval:

```bash
cd /Users/josh/Desktop/Dev-Flow
.venv/bin/python skills/improve-codebase-architecture/scripts/start_rehab_loop.py \
  --repo /Users/josh/Desktop/Dev-Flow \
  --candidate "Tighten Dogfood Harness Mechanics: choose one reviewed Graphify/Ponytail work-queue packet, implement only the current small fix, preserve public behavior, and stop after one test-backed slice." \
  --scorecard /Users/josh/Desktop/Dev-Flow/.devflow/architecture-rehab/scorecards/before-20260628T183217Z.json \
  --worker codex55 \
  --profile dfcodex55 \
  --planner-profile dfcodex55 \
  --planner-toolsets hermes-cli \
  --judge-profile dfcodex55 \
  --max-iterations 1 \
  --session-timeout 1800 \
  --stall-timeout 300
```

---

## Self-Review

- Spec coverage: This plan covers the foundation planner contract, explicit planner toolsets, local candidate queue, subagent scout/reviewer spread, verification gates, and the first safe dry-run/live-loop gate.
- Spec wording scan: No incomplete markers are present. Conditional language is limited to current worktree state where a partial patch may already exist.
- Type consistency: `planner_toolsets` is the single new parameter name across Loop Goal Script runtime, CLI, background launch, Dev-Flow wrapper, and tests.
- Scope check: Implementation is split into small chunks. Foundation runtime work is serialized. Scout/reviewer subagents are read-only and can run in parallel. App-code implementation waits until the foundation gate is verified.
