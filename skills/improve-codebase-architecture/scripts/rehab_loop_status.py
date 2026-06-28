#!/usr/bin/env python3
"""Show Loop-Goal-Script status plus latest rehab evidence."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path
from typing import Any, Callable


DEFAULT_LOOP_SCRIPT = Path("/Users/josh/Desktop/Loop Goal Script/loop.py")
DEFAULT_SCORECARD_DIR = Path(".devflow/architecture-rehab/scorecards")


Runner = Callable[[list[str]], subprocess.CompletedProcess[str]]


def _default_runner(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, check=False)


def _command_result(result: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    return {
        "returncode": result.returncode,
        "stdout": (result.stdout or "").strip(),
        "stderr": (result.stderr or "").strip(),
    }


def _latest_json(directory: Path) -> dict[str, Any] | None:
    candidates = sorted(directory.glob("*.json"), key=lambda path: (path.stat().st_mtime, path.name))
    if not candidates:
        return None
    path = candidates[-1]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        data = {"error": f"invalid json: {exc}"}
    return {"path": path.as_posix(), "data": data}


def _latest_handoff(slug: str | None) -> dict[str, Any] | None:
    hermes_home = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))
    sessions = hermes_home / "sessions"
    if not sessions.exists():
        return None
    pattern = f"handoff-*{slug}*.md" if slug else "handoff-*.md"
    candidates = sorted(sessions.glob(pattern), key=lambda path: (path.stat().st_mtime, path.name))
    if not candidates:
        return None
    path = candidates[-1]
    text = path.read_text(encoding="utf-8", errors="replace")
    return {"path": path.as_posix(), "tail": text[-2000:]}


def collect_status(
    repo: str | Path,
    *,
    loop_script: str | Path = DEFAULT_LOOP_SCRIPT,
    slug: str | None = None,
    runner: Runner | None = None,
) -> dict[str, Any]:
    repo_path = Path(repo).resolve()
    loop_path = Path(loop_script).expanduser()
    run = runner or _default_runner

    status_command = [loop_path.as_posix(), "status"]
    snapshot: dict[str, Any] = {
        "repo": repo_path.as_posix(),
        "loop_status": _command_result(run(status_command)),
        "watch": None,
        "latest_scorecard": _latest_json(repo_path / DEFAULT_SCORECARD_DIR),
        "latest_handoff": _latest_handoff(slug),
    }

    if slug:
        watch_command = [loop_path.as_posix(), "watch", slug, "--once"]
        snapshot["watch"] = _command_result(run(watch_command))

    return snapshot


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".", help="Repository root. Defaults to cwd.")
    parser.add_argument("--loop-script", default=DEFAULT_LOOP_SCRIPT.as_posix(), help="Loop-Goal-Script loop.py path.")
    parser.add_argument("--slug", default=None, help="Optional loop slug to watch once.")
    args = parser.parse_args(argv)

    print(json.dumps(collect_status(args.repo, loop_script=args.loop_script, slug=args.slug), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
