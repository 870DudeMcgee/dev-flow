from __future__ import annotations

import ipaddress
import os
import plistlib
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


DEFAULT_LAUNCH_AGENT_LABEL = "com.devflow.operating-layer"
DEFAULT_OPERATING_LAYER_HOST = "127.0.0.1"
DEFAULT_OPERATING_LAYER_PORT = 8765

_LABEL_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


@dataclass(frozen=True)
class LaunchAgentInstallResult:
    label: str
    plist_path: Path
    url: str
    loaded: bool
    load_command: list[str] | None
    stdout_path: Path
    stderr_path: Path
    launchctl_stdout: str = ""
    launchctl_stderr: str = ""


def install_operating_layer_launch_agent(
    repo_root: Path,
    *,
    host: str = DEFAULT_OPERATING_LAYER_HOST,
    port: int = DEFAULT_OPERATING_LAYER_PORT,
    label: str = DEFAULT_LAUNCH_AGENT_LABEL,
    launch_agents_dir: Path | None = None,
    logs_dir: Path | None = None,
    python_executable: Path | None = None,
    load: bool = False,
    open_browser: bool = False,
    allow_network_host: bool = False,
    run_command: Callable[..., subprocess.CompletedProcess[str]] | None = None,
) -> LaunchAgentInstallResult:
    repo = repo_root.resolve()
    _validate_launch_agent_label(label)
    _validate_port(port)
    if not allow_network_host and not _is_loopback_host(host):
        raise ValueError("Refusing to install a LaunchAgent bound to a non-loopback host without --allow-network-host.")

    agents_dir = (launch_agents_dir or Path.home() / "Library" / "LaunchAgents").expanduser()
    log_dir = (logs_dir or Path.home() / ".devflow" / "logs").expanduser()
    python_path = Path(python_executable or sys.executable).expanduser()
    stdout_path = log_dir / "operating-layer.out.log"
    stderr_path = log_dir / "operating-layer.err.log"
    plist_path = agents_dir / f"{label}.plist"

    agents_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    _write_plist(
        plist_path,
        _launch_agent_payload(
            repo,
            host=host,
            port=port,
            label=label,
            python_executable=python_path,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            open_browser=open_browser,
        ),
    )

    load_command: list[str] | None = None
    launchctl_stdout = ""
    launchctl_stderr = ""
    loaded = False
    if load:
        load_command, launchctl_stdout, launchctl_stderr = _load_launch_agent(
            label,
            plist_path,
            run_command=run_command,
        )
        loaded = True

    return LaunchAgentInstallResult(
        label=label,
        plist_path=plist_path,
        url=f"http://{host}:{port}",
        loaded=loaded,
        load_command=load_command,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        launchctl_stdout=launchctl_stdout,
        launchctl_stderr=launchctl_stderr,
    )


def _launch_agent_payload(
    repo_root: Path,
    *,
    host: str,
    port: int,
    label: str,
    python_executable: Path,
    stdout_path: Path,
    stderr_path: Path,
    open_browser: bool,
) -> dict[str, object]:
    args = [
        str(python_executable),
        "-m",
        "devflow.cli",
        "operating-layer",
        "serve",
        "--host",
        host,
        "--port",
        str(port),
    ]
    if open_browser:
        args.append("--open")
    return {
        "Label": label,
        "ProgramArguments": args,
        "WorkingDirectory": str(repo_root),
        "RunAtLoad": True,
        "KeepAlive": False,
        "ProcessType": "Background",
        "StandardOutPath": str(stdout_path),
        "StandardErrorPath": str(stderr_path),
        "EnvironmentVariables": {
            "PYTHONUNBUFFERED": "1",
            "PYTHONPATH": f"{repo_root / 'src'}:{repo_root}",
        },
    }


def _write_plist(path: Path, payload: dict[str, object]) -> None:
    content = plistlib.dumps(payload, sort_keys=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_bytes(content)
    temporary.replace(path)


def _load_launch_agent(
    label: str,
    plist_path: Path,
    *,
    run_command: Callable[..., subprocess.CompletedProcess[str]] | None,
) -> tuple[list[str], str, str]:
    if sys.platform != "darwin":
        raise ValueError("--load is only available on macOS.")
    runner = run_command or subprocess.run
    domain = f"gui/{os.getuid()}"
    runner(
        ["launchctl", "bootout", f"{domain}/{label}"],
        text=True,
        capture_output=True,
        check=False,
    )
    command = ["launchctl", "bootstrap", domain, str(plist_path)]
    completed = runner(command, text=True, capture_output=True, check=False)
    if completed.returncode != 0:
        stderr = completed.stderr or completed.stdout or f"launchctl bootstrap failed with exit code {completed.returncode}"
        raise RuntimeError(stderr.strip())
    enable = runner(
        ["launchctl", "enable", f"{domain}/{label}"],
        text=True,
        capture_output=True,
        check=False,
    )
    if enable.returncode != 0:
        stderr = enable.stderr or enable.stdout or f"launchctl enable failed with exit code {enable.returncode}"
        raise RuntimeError(stderr.strip())
    return command, completed.stdout or "", completed.stderr or ""


def _is_loopback_host(host: str) -> bool:
    normalized = host.strip().strip("[]")
    if normalized == "localhost":
        return True
    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return False


def _validate_launch_agent_label(label: str) -> None:
    if not _LABEL_PATTERN.match(label):
        raise ValueError("LaunchAgent label may contain only letters, numbers, dots, underscores, and hyphens.")


def _validate_port(port: int) -> None:
    if port < 1 or port > 65535:
        raise ValueError("port must be between 1 and 65535")
