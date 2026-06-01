from __future__ import annotations

import os
import subprocess
from pathlib import Path

from devflow.control_room.log_sanitizer import latest_visible_log_line
from devflow.control_room.models import WorkerInput, WorkerResult


class ShellWorkerAdapter:
    name = "shell"

    def run(self, worker_input: WorkerInput) -> WorkerResult:
        worker_input.workspace_path.mkdir(parents=True, exist_ok=True)
        worker_input.log_file.parent.mkdir(parents=True, exist_ok=True)

        # Basic safe variables that are allowed by default
        DEFAULT_ALLOWLIST = {
            "PATH", "TERM", "LANG", "LC_ALL", "LC_CTYPE", "HOME", "USER",
            "LOGNAME", "SHELL", "PWD", "PYTHONPATH", "VIRTUAL_ENV"
        }
        # Allow user to customize allowlist via DEVFLOW_ENV_ALLOWLIST env var
        custom_allow = os.environ.get("DEVFLOW_ENV_ALLOWLIST", "")
        if custom_allow:
            DEFAULT_ALLOWLIST.update(name.strip() for name in custom_allow.split(",") if name.strip())

        # Clean environment: only keep allowed variables from os.environ
        filtered_env = {k: v for k, v in os.environ.items() if k in DEFAULT_ALLOWLIST}

        # Merge with explicit task worker input environment variables (always allowed)
        final_env = filtered_env | worker_input.env

        with worker_input.log_file.open("w", encoding="utf-8") as log:
            log.write(f"$ {' '.join(worker_input.command)}\n")
            log.flush()
            
            proc = subprocess.Popen(
                worker_input.command,
                cwd=worker_input.workspace_path,
                env=final_env,
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
            )
            
            import time
            start_time = time.time()
            limit_bytes = 10 * 1024 * 1024 # 10 MB limit
            limit_exceeded = False
            timeout = worker_input.timeout_seconds or 300

            while proc.poll() is None:
                # Check log file size to prevent disk filling
                if worker_input.log_file.exists():
                    current_size = worker_input.log_file.stat().st_size
                    if current_size > limit_bytes:
                        limit_exceeded = True
                        proc.kill()
                        break
                
                # Check timeout
                if time.time() - start_time > timeout:
                    proc.kill()
                    proc.wait()
                    log.write(f"\nTimed out after {timeout} seconds.\n")
                    log.flush()
                    latest = _latest_log_line(worker_input.log_file)
                    return WorkerResult(
                        status="timeout",
                        summary=f"Worker timed out after {timeout} seconds",
                        exit_code=None,
                        latest_log_line=latest,
                        result_file=worker_input.result_file,
                        log_file=worker_input.log_file,
                    )
                
                time.sleep(0.1)

            # Ensure process is fully reaped
            proc.wait()

            if limit_exceeded:
                log.write(f"\n[DEVFLOW ERROR] Shell execution output exceeded limit of 10MB. Process terminated.\n")
                log.flush()
                latest = _latest_log_line(worker_input.log_file)
                return WorkerResult(
                    status="worker_failed",
                    summary="Shell execution output exceeded limit of 10MB",
                    exit_code=proc.returncode,
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
    return latest_visible_log_line(path)
