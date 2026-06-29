#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_PROMPT_TEMPLATE = """Reply with exactly two lines:
profile: {profile}
status: advisory smoke ok
Do not claim file edits, tests, task changes, commits, promotion, or push.
"""


def main() -> int:
    args = _parse_args()
    run_id = args.run_id or f"hermes-profile-smoke-{dt.datetime.now(dt.UTC).strftime('%Y%m%dT%H%M%SZ')}"
    run_dir = Path(args.output_root) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    checks: list[dict[str, Any]] = []
    if not args.skip_gpt:
        checks.append(
            _hermes_check(
                run_dir=run_dir,
                check_id=args.gpt_profile,
                profile=args.gpt_profile,
                timeout_seconds=args.timeout_seconds,
                dry_run=args.dry_run,
            )
        )

    if not args.skip_direct_local:
        checks.append(
            _direct_local_check(
                run_dir=run_dir,
                base_url=args.local_base_url,
                model=args.local_model,
                timeout_seconds=args.timeout_seconds,
                dry_run=args.dry_run,
            )
        )

    if args.try_local_hermes:
        checks.append(
            _hermes_check(
                run_dir=run_dir,
                check_id=args.local_hermes_profile,
                profile=args.local_hermes_profile,
                timeout_seconds=args.timeout_seconds,
                dry_run=args.dry_run,
            )
        )

    overall_status = _overall_status(checks, dry_run=args.dry_run)
    manifest = {
        "schema_version": 1,
        "run_id": run_id,
        "run_dir": run_dir.as_posix(),
        "overall_status": overall_status,
        "checks": checks,
        "will_create_tasks": False,
        "will_run_workers": False,
        "will_apply_patch": False,
        "will_verify": False,
        "will_promote": False,
        "will_commit": False,
        "will_push": False,
        "will_write_source": False,
    }
    _write_json(run_dir / "manifest.json", manifest)
    _write_summary(run_dir / "summary.md", manifest)
    print(run_dir.as_posix())
    return 0 if overall_status in {"passed", "dry_run"} else 1


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run bounded advisory smoke checks for Dev-Flow Hermes GPT and local Qwen profiles."
    )
    parser.add_argument("--output-root", default=".devflow/reports/hermes-profile-smoke")
    parser.add_argument("--run-id", default="")
    parser.add_argument("--timeout-seconds", type=float, default=90.0)
    parser.add_argument("--gpt-profile", default="hermes-codex-gpt55")
    parser.add_argument("--local-hermes-profile", default="hermes-qwen32")
    parser.add_argument("--local-base-url", default=os.environ.get("LOCAL_MODEL_BASE_URL", "http://127.0.0.1:8080/v1"))
    parser.add_argument("--local-model", default=os.environ.get("LOCAL_MODEL_ID", "qwen35-9b-mtp"))
    parser.add_argument("--skip-gpt", action="store_true")
    parser.add_argument("--skip-direct-local", action="store_true")
    parser.add_argument("--try-local-hermes", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def _hermes_check(
    *,
    run_dir: Path,
    check_id: str,
    profile: str,
    timeout_seconds: float,
    dry_run: bool,
) -> dict[str, Any]:
    prompt = DEFAULT_PROMPT_TEMPLATE.format(profile=profile)
    prompt_path = run_dir / f"{check_id}.prompt.txt"
    output_path = run_dir / f"{check_id}.output.txt"
    stderr_path = run_dir / f"{check_id}.stderr.txt"
    status_path = run_dir / f"{check_id}.status.json"
    prompt_path.write_text(prompt, encoding="utf-8")

    if dry_run:
        result = _status(
            check_id=check_id,
            kind="hermes_profile",
            status="dry_run",
            profile=profile,
            command=["hermes", "-p", profile, "chat", "-q", "<prompt>"],
            prompt_path=prompt_path,
            output_path=output_path,
            stderr_path=stderr_path,
        )
        _write_json(status_path, result)
        return result

    completed = _run_command(
        ["hermes", "-p", profile, "chat", "-q", prompt],
        timeout_seconds=timeout_seconds,
        output_path=output_path,
        stderr_path=stderr_path,
    )
    result = _status(
        check_id=check_id,
        kind="hermes_profile",
        status="passed" if completed["returncode"] == 0 else "failed",
        profile=profile,
        command=["hermes", "-p", profile, "chat", "-q", "<prompt>"],
        prompt_path=prompt_path,
        output_path=output_path,
        stderr_path=stderr_path,
        returncode=completed["returncode"],
        timed_out=completed["timed_out"],
    )
    _write_json(status_path, result)
    return result


def _direct_local_check(
    *,
    run_dir: Path,
    base_url: str,
    model: str,
    timeout_seconds: float,
    dry_run: bool,
) -> dict[str, Any]:
    check_id = "qwen35-direct"
    prompt = "Reply with exactly: local model smoke test ok"
    prompt_path = run_dir / f"{check_id}.prompt.txt"
    output_path = run_dir / f"{check_id}.output.txt"
    stderr_path = run_dir / f"{check_id}.stderr.txt"
    status_path = run_dir / f"{check_id}.status.json"
    prompt_path.write_text(prompt + "\n", encoding="utf-8")

    if dry_run:
        result = _status(
            check_id=check_id,
            kind="local_openai_compatible",
            status="dry_run",
            profile="hermes-qwen32",
            model=model,
            base_url=base_url,
            prompt_path=prompt_path,
            output_path=output_path,
            stderr_path=stderr_path,
        )
        _write_json(status_path, result)
        return result

    url = f"{base_url.rstrip('/')}/chat/completions"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.0,
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    status = "failed"
    error = None
    content = ""
    try:
        with urllib.request.urlopen(req, timeout=timeout_seconds) as response:
            body = response.read().decode("utf-8")
        output_path.write_text(body + "\n", encoding="utf-8")
        response_json = json.loads(body)
        content = (
            response_json.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
            .strip()
        )
        status = "passed" if content else "failed"
        stderr_path.write_text("", encoding="utf-8")
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        error = str(exc)
        stderr_path.write_text(error + "\n", encoding="utf-8")
        output_path.write_text("", encoding="utf-8")

    result = _status(
        check_id=check_id,
        kind="local_openai_compatible",
        status=status,
        profile="hermes-qwen32",
        model=model,
        base_url=base_url,
        prompt_path=prompt_path,
        output_path=output_path,
        stderr_path=stderr_path,
        response_excerpt=content[:200],
        error=error,
    )
    _write_json(status_path, result)
    return result


def _run_command(
    command: list[str],
    *,
    timeout_seconds: float,
    output_path: Path,
    stderr_path: Path,
) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        output_path.write_text(completed.stdout, encoding="utf-8")
        stderr_path.write_text(completed.stderr, encoding="utf-8")
        return {"returncode": completed.returncode, "timed_out": False}
    except subprocess.TimeoutExpired as exc:
        output_path.write_text(_coerce_text(exc.stdout), encoding="utf-8")
        stderr_path.write_text(_coerce_text(exc.stderr) + "Timed out.\n", encoding="utf-8")
        return {"returncode": 124, "timed_out": True}


def _coerce_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _status(
    *,
    check_id: str,
    kind: str,
    status: str,
    profile: str,
    prompt_path: Path,
    output_path: Path,
    stderr_path: Path,
    command: list[str] | None = None,
    model: str | None = None,
    base_url: str | None = None,
    returncode: int | None = None,
    timed_out: bool = False,
    response_excerpt: str | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    return {
        "id": check_id,
        "kind": kind,
        "status": status,
        "profile": profile,
        "model": model,
        "base_url": base_url,
        "command": command,
        "returncode": returncode,
        "timed_out": timed_out,
        "prompt_path": prompt_path.as_posix(),
        "output_path": output_path.as_posix(),
        "stderr_path": stderr_path.as_posix(),
        "response_excerpt": response_excerpt,
        "error": error,
    }


def _overall_status(checks: list[dict[str, Any]], *, dry_run: bool) -> str:
    if dry_run:
        return "dry_run"
    return "passed" if checks and all(check["status"] == "passed" for check in checks) else "failed"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_summary(path: Path, manifest: dict[str, Any]) -> None:
    lines = [
        "# Hermes Profile Smoke",
        "",
        f"- Run ID: `{manifest['run_id']}`",
        f"- Overall status: `{manifest['overall_status']}`",
        "- Scope: advisory evidence only; no task state, source files, git state, promotion, or push.",
        "",
        "## Checks",
    ]
    for check in manifest["checks"]:
        lines.append(f"- `{check['id']}`: `{check['status']}` ({check['kind']})")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
