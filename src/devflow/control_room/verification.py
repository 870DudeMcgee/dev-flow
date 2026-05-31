from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from devflow.control_room.log_sanitizer import latest_visible_log_line


@dataclass(frozen=True)
class VerificationResult:
    status: str
    command: list[str]
    exit_code: int | None
    latest_log_line: str
    log_file: Path


def run_verification_command(workspace: Path, command: list[str], log_file: Path, timeout_seconds: int = 120) -> VerificationResult:
    workspace.mkdir(parents=True, exist_ok=True)
    log_file.parent.mkdir(parents=True, exist_ok=True)

    with log_file.open("w", encoding="utf-8") as log:
        log.write(f"$ {' '.join(command)}\n")
        log.flush()
        proc = subprocess.Popen(
            command,
            cwd=workspace,
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
        )
        try:
            proc.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            log.write(f"\nVerification timed out after {timeout_seconds} seconds.\n")
            log.flush()
            return VerificationResult(
                status="timeout",
                command=command,
                exit_code=None,
                latest_log_line=_latest_log_line(log_file),
                log_file=log_file,
            )

    return VerificationResult(
        status="passed" if proc.returncode == 0 else "failed",
        command=command,
        exit_code=proc.returncode,
        latest_log_line=_latest_log_line(log_file),
        log_file=log_file,
    )


def _latest_log_line(path: Path) -> str:
    return latest_visible_log_line(path)
