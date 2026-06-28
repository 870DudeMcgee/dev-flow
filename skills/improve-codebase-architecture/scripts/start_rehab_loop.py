#!/usr/bin/env python3
"""Create a rehab goal file and optionally start Loop-Goal-Script."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


DEFAULT_LOOP_SCRIPT = Path("/Users/josh/Desktop/Loop Goal Script/loop.py")
DEFAULT_GOAL_DIR = Path(".devflow/architecture-rehab/goals")
DEFAULT_WORKER = "local-fast"
GOAL_TEMPLATES = ("auto", "rehab", "smoke")
WORKER_PROFILES = {
    "local-fast": "dflocalfast",
    "codex55": "dfcodex55",
}
DEFAULT_SAFE_PROFILE = WORKER_PROFILES[DEFAULT_WORKER]
DEFAULT_JUDGE_PROFILE = WORKER_PROFILES["codex55"]
DEFAULT_PLANNER_PROFILE = WORKER_PROFILES["codex55"]
DEFAULT_SMOKE_SESSION_TIMEOUT = 120
DEFAULT_SMOKE_HERMES_MAX_TURNS = 2
DEFAULT_SMOKE_HERMES_TOOLSETS = "terminal"
DEFAULT_CODEX55_REHAB_TOOLSETS = "terminal"
LOCAL_HOST_MARKERS = ("127.0.0.1", "localhost", "[::1]")
Runner = Callable[[list[str]], subprocess.CompletedProcess[str] | None]
PreflightChecker = Callable[[str], dict[str, Any]]


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def _slugify(text: str, max_len: int = 60) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower().strip()).strip("-")
    if len(slug) <= max_len:
        return slug
    digest = hashlib.md5(text.encode()).hexdigest()[:6]
    return slug[: max_len - 7] + "-" + digest


def _resolve_profile(worker: str, profile: str | None) -> str:
    if profile:
        return profile
    try:
        return WORKER_PROFILES[worker]
    except KeyError as exc:
        allowed = ", ".join(sorted(WORKER_PROFILES))
        raise ValueError(f"Unknown worker preset {worker!r}. Use one of: {allowed}") from exc


def _resolve_goal_template(repo: Path, candidate: str, goal_template: str) -> str:
    if goal_template not in GOAL_TEMPLATES:
        allowed = ", ".join(GOAL_TEMPLATES)
        raise ValueError(f"Unknown goal template {goal_template!r}. Use one of: {allowed}")
    if goal_template != "auto":
        return goal_template
    marker = f"{repo.name} {candidate}".lower()
    return "smoke" if "smoke" in marker else "rehab"


def _goal_text(
    repo: Path,
    *,
    candidate: str,
    scorecard: Path | None,
    max_iterations: int,
    worker: str,
    profile: str,
    planner_profile: str | None,
    judge_profile: str | None,
) -> str:
    scorecard_line = scorecard.as_posix() if scorecard else "Run graphify_rehab_score.py first if no fresh scorecard exists."
    return f"""# Graphify Ponytail Architecture Rehab Goal

Repository: {repo.as_posix()}
Candidate: {candidate}
Iteration budget: {max_iterations}
Worker preset: {worker}
Worker profile: {profile}
Planner profile: {planner_profile or "(disabled)"}
Judge profile: {judge_profile or "(disabled)"}
Scorecard: {scorecard_line}

Use Loop-Goal-Script as the loop engine. Do not reimplement loop mechanics.

## Mission

Maintain a codebase-wide refactor direction, then complete one safe architecture slice that improves locality or leverage with Graphify evidence and Ponytail gates.

## Planner Gate

Before worker implementation starts, the planner must analyze the repository state, Graphify evidence, improve-codebase-architecture guidance, and Ponytail pressure.

The planner must produce a worker plan with:

- Codebase-wide refactor direction.
- Current small, testable fix.
- Exact files, focused tests, verification commands, and stop conditions.

The worker must not edit source until the planner plan exists, and must implement only the Current Small Fix.

## Hard Stops

- Work on one safe architecture slice only.
- Do not commit generated graphify-out/ files.
- Do not push, publish, open PRs, promote, or merge.
- Stop and hand off if the graph is stale, tests cannot run, or the slice needs a wider product decision.
- Treat Graphify as evidence, not authority; verify every claim against source and tests.

## Required Loop Evidence

1. Refresh or read Graphify evidence.
2. Record a before scorecard.
3. Apply the smallest slice that deletes, reuses, or deepens real implementation.
4. Run focused tests for touched behavior.
5. Record an after scorecard and compare deltas.
6. Write a markdown handoff with Status, Outcome, Files Changed, Verification, Risks, Recommended Next Steps, and Next Safe Action.

## Progress Rule

Progress is trusted only when the handoff cites code changes, passing focused tests, and graph delta evidence. Rephrased plans are not progress.
"""


def _smoke_goal_text(
    repo: Path,
    *,
    candidate: str,
    max_iterations: int,
    worker: str,
    profile: str,
) -> str:
    return f"""# Loop-Goal-Script Smoke Test

Repository: {repo.as_posix()}
Candidate: {candidate}
Iteration budget: {max_iterations}
Worker preset: {worker}
Worker profile: {profile}

Use Loop-Goal-Script as the loop engine. This is a lifecycle smoke test, not an architecture rehab run.

## Mission

Prove that the loop can inspect this tiny repository, run a bounded verification command, write one structured handoff, report status, and exit after one iteration.

## Hard Stops

- Do not edit source files.
- Do not run Graphify, scorecards, promotion, push, merge, PR, or cleanup commands.
- Stay inside the repository listed above.
- Stop and write a handoff if pytest is unavailable, verification cannot run, or the repo is not the expected tiny smoke fixture.

## Required Smoke Evidence

1. Inspect the repository files.
2. Run `python -m pytest -q` if Python and pytest are available.
3. Run `git status --short`.
4. Write a markdown handoff with Completed, Remaining, Active State, Blockers / Decisions, Errors, and Next Action.

## Progress Rule

Progress is trusted only when the handoff cites the inspected files, verification result or reason it could not run, and git status. Rephrased plans are not progress.
"""


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
    command = [
        loop_script.as_posix(),
        "start",
        "--goal-file",
        goal_file.as_posix(),
        "--workdir",
        repo.as_posix(),
        "--max-iterations",
        str(max_iterations),
        "--profile",
        profile,
    ]
    if no_judge:
        command.append("--no-judge")
    elif judge_profile:
        command.extend(["--judge-profile", judge_profile])
    if not no_judge and planner_profile:
        command.extend(["--planner-profile", planner_profile])
    if not no_judge and planner_toolsets:
        command.extend(["--planner-toolsets", planner_toolsets])
    if session_timeout is not None:
        command.extend(["--session-timeout", str(session_timeout)])
    if stall_timeout is not None:
        command.extend(["--stall-timeout", str(stall_timeout)])
    if hermes_max_turns is not None:
        command.extend(["--hermes-max-turns", str(hermes_max_turns)])
    if hermes_toolsets:
        command.extend(["--hermes-toolsets", hermes_toolsets])
    if hermes_ignore_rules:
        command.append("--hermes-ignore-rules")
    if background:
        command.append("--background")
    return command


def _read_model_config(config_path: Path) -> dict[str, str]:
    if not config_path.exists():
        return {}
    values: dict[str, str] = {}
    in_model = False
    for line in config_path.read_text(encoding="utf-8").splitlines():
        if line == "model:":
            in_model = True
            continue
        if in_model and line and not line.startswith(" "):
            break
        if not in_model or ":" not in line:
            continue
        key, raw_value = line.split(":", 1)
        key = key.strip()
        if key in {"default", "provider", "base_url"}:
            values[key] = raw_value.strip().strip("'\"")
    return values


def _default_get_json(url: str) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=2) as response:
        return json.loads(response.read().decode("utf-8"))


def _local_health_url(base_url: str) -> str:
    root = base_url.rstrip("/")
    if root.endswith("/v1"):
        root = root[:-3]
    return f"{root}/health"


def _model_ids(payload: dict[str, Any]) -> set[str]:
    rows = payload.get("data") or payload.get("models") or []
    ids: set[str] = set()
    for row in rows:
        if isinstance(row, dict):
            ids.update(str(row.get(key) or "") for key in ("id", "model", "name"))
    return {value for value in ids if value}


def preflight_profile(
    profile: str,
    *,
    hermes_home: str | Path | None = None,
    get_json: Callable[[str], dict[str, Any]] = _default_get_json,
) -> dict[str, Any]:
    home = Path(hermes_home or Path.home() / ".hermes")
    config_path = home / "config.yaml" if profile in {"", "default"} else home / "profiles" / profile / "config.yaml"
    model_config = _read_model_config(config_path)
    if not model_config:
        return {
            "ok": False,
            "profile": profile,
            "reason": f"Hermes profile config not found or missing model block: {config_path}",
        }

    model = model_config.get("default", "")
    base_url = model_config.get("base_url", "")
    result: dict[str, Any] = {
        "ok": True,
        "profile": profile,
        "model": model,
        "base_url": base_url,
        "config": config_path.as_posix(),
    }

    if not any(marker in base_url for marker in LOCAL_HOST_MARKERS):
        result["reason"] = "remote profile; local model preflight skipped"
        return result

    try:
        health = get_json(_local_health_url(base_url))
        models = get_json(f"{base_url.rstrip('/')}/models")
    except (OSError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return {**result, "ok": False, "reason": f"local endpoint unavailable: {exc}"}

    available = _model_ids(models)
    if model and model not in available:
        return {**result, "ok": False, "reason": f"model {model!r} not listed by local endpoint", "models": sorted(available)}
    result["health"] = health
    result["models"] = sorted(available)
    return result


def prepare_rehab_loop(
    repo: str | Path,
    *,
    candidate: str,
    loop_script: str | Path = DEFAULT_LOOP_SCRIPT,
    goal_dir: str | Path | None = None,
    scorecard: str | Path | None = None,
    max_iterations: int = 1,
    worker: str = DEFAULT_WORKER,
    profile: str | None = None,
    goal_template: str = "auto",
    no_judge: bool | None = None,
    judge_profile: str | None = None,
    planner_profile: str | None = None,
    planner_toolsets: str | None = None,
    stall_timeout: int | None = None,
    session_timeout: int | None = None,
    hermes_max_turns: int | None = None,
    hermes_toolsets: str | None = None,
    hermes_ignore_rules: bool | None = None,
    background: bool = False,
    dry_run: bool = False,
    skip_preflight: bool = False,
    preflight_checker: PreflightChecker | None = None,
    runner: Runner | None = None,
    timestamp: str | None = None,
) -> dict[str, Any]:
    repo_path = Path(repo).resolve()
    loop_path = Path(loop_script).expanduser()
    selected_profile = _resolve_profile(worker, profile)
    selected_goal_template = _resolve_goal_template(repo_path, candidate, goal_template)
    selected_no_judge = selected_goal_template == "smoke" if no_judge is None else no_judge
    selected_session_timeout = session_timeout
    selected_hermes_max_turns = hermes_max_turns
    selected_hermes_toolsets = hermes_toolsets
    selected_planner_toolsets = planner_toolsets
    selected_hermes_ignore_rules = hermes_ignore_rules
    if selected_goal_template == "smoke":
        if selected_session_timeout is None:
            selected_session_timeout = DEFAULT_SMOKE_SESSION_TIMEOUT
        if selected_hermes_max_turns is None:
            selected_hermes_max_turns = DEFAULT_SMOKE_HERMES_MAX_TURNS
        if selected_hermes_toolsets is None:
            selected_hermes_toolsets = DEFAULT_SMOKE_HERMES_TOOLSETS
        if selected_hermes_ignore_rules is None:
            selected_hermes_ignore_rules = True
    elif selected_hermes_ignore_rules is None:
        selected_hermes_ignore_rules = False
    if selected_goal_template == "rehab" and worker == "codex55":
        if selected_planner_toolsets is None:
            selected_planner_toolsets = DEFAULT_CODEX55_REHAB_TOOLSETS
        if selected_hermes_toolsets is None:
            selected_hermes_toolsets = DEFAULT_CODEX55_REHAB_TOOLSETS
    selected_judge_profile = None
    selected_planner_profile = None
    if not selected_no_judge:
        selected_judge_profile = judge_profile
        if selected_judge_profile is None and selected_goal_template == "rehab":
            selected_judge_profile = DEFAULT_JUDGE_PROFILE
        selected_planner_profile = planner_profile
        if selected_planner_profile is None and selected_goal_template == "rehab":
            selected_planner_profile = selected_judge_profile or DEFAULT_PLANNER_PROFILE
    goals = Path(goal_dir) if goal_dir else repo_path / DEFAULT_GOAL_DIR
    goals.mkdir(parents=True, exist_ok=True)
    stamp = timestamp or _timestamp()
    goal_id = _slugify(f"{worker}-{candidate}", 48) or "goal"
    goal_file = goals / f"{selected_goal_template}-{stamp}-{goal_id}.md"
    scorecard_path = Path(scorecard).resolve() if scorecard else None
    if selected_goal_template == "smoke":
        goal_text = _smoke_goal_text(
            repo_path,
            candidate=candidate,
            max_iterations=max_iterations,
            worker=worker,
            profile=selected_profile,
        )
    else:
        goal_text = _goal_text(
            repo_path,
            candidate=candidate,
            scorecard=scorecard_path,
            max_iterations=max_iterations,
            worker=worker,
            profile=selected_profile,
            planner_profile=selected_planner_profile,
            judge_profile=selected_judge_profile,
        )
    goal_file.write_text(goal_text, encoding="utf-8")
    command = _command(
        loop_path,
        goal_file,
        repo_path,
        max_iterations,
        background,
        selected_profile,
        no_judge=selected_no_judge,
        judge_profile=selected_judge_profile,
        planner_profile=selected_planner_profile,
        planner_toolsets=selected_planner_toolsets,
        stall_timeout=stall_timeout,
        session_timeout=selected_session_timeout,
        hermes_max_turns=selected_hermes_max_turns,
        hermes_toolsets=selected_hermes_toolsets,
        hermes_ignore_rules=selected_hermes_ignore_rules,
    )
    loop_slug = _slugify(goal_text.strip())
    hermes_home = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))

    result: dict[str, Any] = {
        "goal_file": goal_file.as_posix(),
        "command": command,
        "worker": worker,
        "profile": selected_profile,
        "planner_profile": selected_planner_profile,
        "planner_toolsets": selected_planner_toolsets,
        "judge_profile": selected_judge_profile,
        "goal_template": selected_goal_template,
        "session_timeout": selected_session_timeout,
        "hermes_max_turns": selected_hermes_max_turns,
        "hermes_toolsets": selected_hermes_toolsets,
        "hermes_ignore_rules": selected_hermes_ignore_rules,
        "loop_slug": loop_slug,
        "loop_log": (hermes_home / "logs" / f"loop-{loop_slug}.log").as_posix(),
        "loop_pid": (hermes_home / "logs" / f"loop-{loop_slug}.pid").as_posix(),
        "started": False,
        "dry_run": dry_run,
    }
    if dry_run:
        return result

    if not skip_preflight:
        checker = preflight_checker or preflight_profile
        preflight = checker(selected_profile)
        result["preflight"] = preflight
        if not preflight.get("ok"):
            result["returncode"] = 2
            return result
        aux_profiles = [
            profile
            for profile in (selected_planner_profile, selected_judge_profile)
            if profile and profile != selected_profile
        ]
        checked: dict[str, dict[str, Any]] = {}
        for aux_profile in dict.fromkeys(aux_profiles):
            checked[aux_profile] = checker(aux_profile)
        if selected_planner_profile and selected_planner_profile != selected_profile:
            result["planner_preflight"] = checked[selected_planner_profile]
        if selected_judge_profile and selected_judge_profile != selected_profile:
            result["judge_preflight"] = checked[selected_judge_profile]
        for aux_profile, aux_preflight in checked.items():
            if not aux_preflight.get("ok"):
                result["returncode"] = 2
                return result

    completed = (runner or (lambda cmd: subprocess.run(cmd, text=True, check=False)))(command)
    returncode = completed.returncode if completed is not None else 0
    result["started"] = returncode == 0
    result["returncode"] = returncode
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".", help="Repository root. Defaults to cwd.")
    parser.add_argument("--candidate", required=True, help="Architecture slice candidate.")
    parser.add_argument("--scorecard", default=None, help="Optional scorecard JSON path to cite in the goal.")
    parser.add_argument("--goal-dir", default=None, help="Goal output directory.")
    parser.add_argument("--loop-script", default=DEFAULT_LOOP_SCRIPT.as_posix(), help="Loop-Goal-Script loop.py path.")
    parser.add_argument("--max-iterations", type=int, default=1, help="Loop iteration cap.")
    parser.add_argument(
        "--worker",
        choices=sorted(WORKER_PROFILES),
        default=DEFAULT_WORKER,
        help="Named worker preset. local-fast uses qwen35-9b-mtp; codex55 uses Hermes GPT Codex 5.5.",
    )
    parser.add_argument(
        "--goal-template",
        choices=GOAL_TEMPLATES,
        default="auto",
        help="Goal template. auto selects smoke for smoke repos/candidates, otherwise rehab.",
    )
    parser.add_argument("--profile", default=None, help="Hermes profile override passed to Loop-Goal-Script.")
    parser.add_argument("--no-judge", action="store_true", help="Pass --no-judge to Loop-Goal-Script.")
    parser.add_argument(
        "--judge-profile",
        default=None,
        help="Hermes profile used for Loop-Goal-Script judge calls. Rehab runs default to dfcodex55.",
    )
    parser.add_argument(
        "--planner-profile",
        default=None,
        help="Hermes profile used for Loop-Goal-Script planner calls. Rehab runs default to dfcodex55.",
    )
    parser.add_argument(
        "--planner-toolsets",
        default=None,
        help="Hermes toolsets used for Loop-Goal-Script planner calls.",
    )
    parser.add_argument(
        "--session-timeout",
        type=int,
        default=None,
        help="Optional Loop-Goal-Script total session timeout. Smoke defaults to 120 seconds.",
    )
    parser.add_argument("--stall-timeout", type=int, default=None, help="Optional Loop-Goal-Script stall timeout.")
    parser.add_argument(
        "--hermes-max-turns",
        type=int,
        default=None,
        help="Optional Hermes worker max-turns cap. Smoke defaults to 2.",
    )
    parser.add_argument(
        "--hermes-toolsets",
        default=None,
        help="Optional comma-separated Hermes worker toolsets. Smoke defaults to terminal.",
    )
    parser.add_argument(
        "--hermes-ignore-rules",
        action="store_true",
        help="Pass --ignore-rules to the Hermes worker. Smoke enables this by default.",
    )
    parser.add_argument("--background", action="store_true", help="Pass --background to Loop-Goal-Script.")
    parser.add_argument("--dry-run", action="store_true", help="Write the goal and print the command without launching.")
    parser.add_argument("--skip-preflight", action="store_true", help="Skip profile/server checks before a real start.")
    args = parser.parse_args(argv)

    result = prepare_rehab_loop(
        args.repo,
        candidate=args.candidate,
        loop_script=args.loop_script,
        goal_dir=args.goal_dir,
        scorecard=args.scorecard,
        max_iterations=args.max_iterations,
        worker=args.worker,
        profile=args.profile,
        goal_template=args.goal_template,
        no_judge=True if args.no_judge else None,
        judge_profile=args.judge_profile,
        planner_profile=args.planner_profile,
        planner_toolsets=args.planner_toolsets,
        session_timeout=args.session_timeout,
        stall_timeout=args.stall_timeout,
        hermes_max_turns=args.hermes_max_turns,
        hermes_toolsets=args.hermes_toolsets,
        hermes_ignore_rules=True if args.hermes_ignore_rules else None,
        background=args.background,
        dry_run=args.dry_run,
        skip_preflight=args.skip_preflight,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("started") or args.dry_run else int(result.get("returncode", 1))


if __name__ == "__main__":
    raise SystemExit(main())
