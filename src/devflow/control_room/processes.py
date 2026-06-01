from __future__ import annotations

import os
import signal
import subprocess
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