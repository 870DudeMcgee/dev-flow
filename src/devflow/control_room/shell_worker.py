from __future__ import annotations

import subprocess
from pathlib import Path

from devflow.control_room.models import WorkerInput, WorkerResult


class ShellWorkerAdapter:
    name = "shell"

    def run(self, worker_input: WorkerInput) -> WorkerResult:
        worker_input.workspace_path.mkdir(parents=True, exist_ok=True)
        worker_input.log_file.parent.mkdir(parents=True, exist_ok=True)

        with worker_input.log_file.open("w", encoding="utf-8") as log:
            log.write(f"$ {' '.join(worker_input.command)}\n")
            log.flush()
            proc = subprocess.Popen(
                worker_input.command,
                cwd=worker_input.workspace_path,
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
            )
            try:
                proc.wait(timeout=worker_input.timeout_seconds)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
                log.write(f"\nTimed out after {worker_input.timeout_seconds} seconds.\n")
                log.flush()
                latest = _latest_log_line(worker_input.log_file)
                return WorkerResult(
                    status="timeout",
                    summary=f"Worker timed out after {worker_input.timeout_seconds} seconds",
                    exit_code=None,
                    latest_log_line=latest,
                    result_file=worker_input.result_file,
                    log_file=worker_input.log_file,
                )

        latest = _latest_log_line(worker_input.log_file)
        if proc.returncode == 0:
            return WorkerResult(
                status="complete",
                summary="Worker completed successfully",
                exit_code=0,
                latest_log_line=latest,
                result_file=worker_input.result_file,
                log_file=worker_input.log_file,
            )

        return WorkerResult(
            status="worker_failed",
            summary=f"Worker exited with {proc.returncode}",
            exit_code=proc.returncode,
            latest_log_line=latest,
            result_file=worker_input.result_file,
            log_file=worker_input.log_file,
        )


def _latest_log_line(path: Path) -> str:
    if not path.exists():
        return ""
    lines = [line.strip() for line in path.read_text(encoding="utf-8", errors="replace").splitlines()]
    return next((line for line in reversed(lines) if line), "")
