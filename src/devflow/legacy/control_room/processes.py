from __future__ import annotations

import os
import signal
import subprocess
import time
from typing import Any


def start_process(command: list[str], **kwargs: Any) -> subprocess.Popen[Any]:
    if os.name == "posix":
        kwargs["start_new_session"] = True
    return subprocess.Popen(command, **kwargs)


def kill_process_tree(process: subprocess.Popen[Any]) -> None:
    if process.poll() is not None:
        return
    if os.name == "posix":
        try:
            os.killpg(process.pid, signal.SIGKILL)
            return
        except ProcessLookupError:
            return
        except OSError:
            pass
    process.kill()


def _wait_for_process_reap(process: subprocess.Popen[Any], timeout_seconds: float, poll_interval_seconds: float = 0.05) -> bool:
    deadline = time.monotonic() + max(timeout_seconds, 0)
    while time.monotonic() < deadline:
        if process.poll() is not None:
            return True
        time.sleep(poll_interval_seconds)
    return process.poll() is not None


def cleanup_process_tree(process: subprocess.Popen[Any], timeout_seconds: float = 1.0, retry_count: int = 1) -> bool:
    if process.poll() is not None:
        return True

    for _ in range(max(retry_count, 0) + 1):
        kill_process_tree(process)
        if _wait_for_process_reap(process, timeout_seconds=timeout_seconds):
            return True

    return False
