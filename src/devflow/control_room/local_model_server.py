from __future__ import annotations

import json
import os
import shlex
import signal
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal
from urllib.parse import urlparse

from devflow.control_room.paths import devflow_dir, relative_path


LocalModelServerKind = Literal["llama-server", "ollama"]


class LocalModelServerError(ValueError):
    """Raised when a local model server lifecycle action is unsafe."""


@dataclass(frozen=True)
class LocalModelServerProfile:
    profile_id: str
    provider: str
    model: str
    host: str
    port: int
    base_url: str
    command: list[str]
    aliases: tuple[str, ...] = ()

    def model_dump(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "provider": self.provider,
            "model": self.model,
            "host": self.host,
            "port": self.port,
            "base_url": self.base_url,
            "command": list(self.command),
            "aliases": list(self.aliases),
        }


@dataclass(frozen=True)
class LocalModelServerProcess:
    pid: int
    ppid: int | None
    stat: str
    rss_kb: int | None
    command: str
    kind: LocalModelServerKind
    provider: str | None
    model: str | None
    alias: str | None
    port: int | None
    managed_by_default: bool

    def model_dump(self) -> dict[str, Any]:
        return {
            "pid": self.pid,
            "ppid": self.ppid,
            "stat": self.stat,
            "rss_kb": self.rss_kb,
            "command": self.command,
            "kind": self.kind,
            "provider": self.provider,
            "model": self.model,
            "alias": self.alias,
            "port": self.port,
            "managed_by_default": self.managed_by_default,
        }


KillFunc = Callable[[int, int], None]
ProcessLister = Callable[[], list[LocalModelServerProcess]]
ProcessActive = Callable[[int], bool]
Sleeper = Callable[[float], None]
PopenFactory = Callable[..., Any]
StartProfile = Callable[..., dict[str, Any]]


def qwen35_mtp_profile(
    *,
    host: str = "127.0.0.1",
    port: int = 8080,
    binary: str = "llama-server",
) -> LocalModelServerProfile:
    model = "qwen35-9b-mtp"
    command = [
        binary,
        "--hf-repo",
        "unsloth/Qwen3.5-9B-MTP-GGUF:UD-Q4_K_XL",
        "--no-mmproj",
        "--alias",
        model,
        "--host",
        host,
        "--port",
        str(port),
        "--ctx-size",
        "65536",
        "--gpu-layers",
        "99",
        "--flash-attn",
        "on",
        "--parallel",
        "1",
        "--cache-type-k",
        "q8_0",
        "--cache-type-v",
        "q8_0",
        "--cache-type-k-draft",
        "q8_0",
        "--cache-type-v-draft",
        "q8_0",
        "--cache-ram",
        "4096",
        "--ctx-checkpoints",
        "8",
        "--checkpoint-min-step",
        "2048",
        "--cache-idle-slots",
        "--spec-type",
        "draft-mtp",
        "--spec-draft-n-max",
        "6",
        "--chat-template-kwargs",
        '{"enable_thinking":false}',
        "--no-webui",
    ]
    return LocalModelServerProfile(
        profile_id="qwen35-mtp",
        provider="qwen35-mtp",
        model=model,
        host=host,
        port=port,
        base_url=f"http://{host}:{port}/v1",
        command=command,
        aliases=("local-qwen35-mtp", "dflocalfast", "df-local-fast"),
    )


def known_local_model_server_profiles(
    *,
    host: str = "127.0.0.1",
    port: int = 8080,
    binary: str = "llama-server",
) -> dict[str, LocalModelServerProfile]:
    qwen = qwen35_mtp_profile(host=host, port=port, binary=binary)
    profiles: dict[str, LocalModelServerProfile] = {qwen.profile_id: qwen}
    for alias in qwen.aliases:
        profiles[alias] = qwen
    return profiles


def resolve_local_model_server_profile(
    profile: str,
    *,
    host: str = "127.0.0.1",
    port: int = 8080,
    binary: str = "llama-server",
) -> LocalModelServerProfile:
    profiles = known_local_model_server_profiles(host=host, port=port, binary=binary)
    try:
        return profiles[profile]
    except KeyError as exc:
        valid = ", ".join(sorted(profiles))
        raise LocalModelServerError(f"Unknown local model server profile '{profile}'. Valid profiles: {valid}") from exc


def list_local_model_server_processes(*, include_ollama: bool = False) -> list[LocalModelServerProcess]:
    try:
        result = subprocess.run(
            ["ps", "-axo", "pid=,ppid=,stat=,rss=,command="],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return []
    return parse_local_model_server_processes(result.stdout, include_ollama=include_ollama)


def parse_local_model_server_processes(
    ps_output: str,
    *,
    include_ollama: bool = False,
) -> list[LocalModelServerProcess]:
    processes: list[LocalModelServerProcess] = []
    for raw_line in ps_output.splitlines():
        parsed = _parse_ps_line(raw_line)
        if parsed is None:
            continue
        pid, ppid, stat, rss_kb, command = parsed
        if pid == os.getpid():
            continue
        process = _classify_local_model_process(
            pid=pid,
            ppid=ppid,
            stat=stat,
            rss_kb=rss_kb,
            command=command,
        )
        if process is None:
            continue
        if process.kind == "ollama" and not include_ollama:
            continue
        processes.append(process)
    return processes


def local_model_server_status(*, include_ollama: bool = False) -> dict[str, Any]:
    processes = list_local_model_server_processes(include_ollama=include_ollama)
    return {
        "status": "running" if processes else "idle",
        "running_count": len(processes),
        "processes": [process.model_dump() for process in processes],
        "managed_profiles": [
            profile.model_dump()
            for key, profile in known_local_model_server_profiles().items()
            if key == profile.profile_id
        ],
        "notes": [
            "Default stop/start management targets llama-server processes.",
            "Ollama is shown only with --include-ollama and is not stopped by default.",
        ],
    }


def stop_local_model_servers(
    root: Path,
    *,
    profile: str | None = None,
    include_ollama: bool = False,
    dry_run: bool = False,
    timeout_seconds: float = 15.0,
    force_after_timeout: bool = True,
    process_lister: ProcessLister | None = None,
    kill_func: KillFunc | None = None,
    is_process_active: ProcessActive | None = None,
    sleeper: Sleeper | None = None,
) -> dict[str, Any]:
    lister = process_lister or (lambda: list_local_model_server_processes(include_ollama=include_ollama))
    kill = kill_func or os.kill
    active = is_process_active or _process_is_active
    sleep = sleeper or time.sleep
    processes = _filter_processes(lister(), profile=profile, include_ollama=include_ollama)
    started_at = _utc_now()
    run_dir = _server_profile_dir(root, profile or "all")
    payload: dict[str, Any] = {
        "action": "stop",
        "status": "idle" if not processes else "would_stop" if dry_run else "stopped",
        "started_at": started_at,
        "profile": profile,
        "include_ollama": include_ollama,
        "dry_run": dry_run,
        "timeout_seconds": timeout_seconds,
        "force_after_timeout": force_after_timeout,
        "processes": [process.model_dump() for process in processes],
        "stopped_pids": [],
        "escalated_pids": [],
        "errors": [],
    }
    if not processes or dry_run:
        _write_server_manifest(root, run_dir, payload)
        return payload

    for process in processes:
        try:
            kill(process.pid, signal.SIGTERM)
            payload["stopped_pids"].append(process.pid)
        except (ProcessLookupError, PermissionError, OSError) as exc:
            payload["errors"].append(f"SIGTERM {process.pid}: {exc}")

    deadline = time.monotonic() + max(timeout_seconds, 0)
    while time.monotonic() < deadline:
        if not any(active(process.pid) for process in processes):
            break
        sleep(0.2)

    if force_after_timeout:
        for process in processes:
            if not active(process.pid):
                continue
            try:
                kill(process.pid, signal.SIGKILL)
                payload["escalated_pids"].append(process.pid)
            except (ProcessLookupError, PermissionError, OSError) as exc:
                payload["errors"].append(f"SIGKILL {process.pid}: {exc}")
    elif any(active(process.pid) for process in processes):
        payload["status"] = "timeout"

    payload["completed_at"] = _utc_now()
    _write_server_manifest(root, run_dir, payload)
    return payload


def start_local_model_server(
    root: Path,
    profile: str = "qwen35-mtp",
    *,
    host: str = "127.0.0.1",
    port: int = 8080,
    binary: str = "llama-server",
    replace: bool = False,
    dry_run: bool = False,
    wait_for_ready: bool = True,
    ready_timeout_seconds: float = 60.0,
    process_lister: ProcessLister | None = None,
    kill_func: KillFunc | None = None,
    is_process_active: ProcessActive | None = None,
    sleeper: Sleeper | None = None,
    popen_factory: PopenFactory | None = None,
) -> dict[str, Any]:
    server_profile = resolve_local_model_server_profile(profile, host=host, port=port, binary=binary)
    lister = process_lister or (lambda: list_local_model_server_processes(include_ollama=False))
    existing = _filter_processes(lister(), include_ollama=False)
    if existing and not replace:
        pids = ", ".join(str(process.pid) for process in existing)
        raise LocalModelServerError(
            f"Local model server already running as pid(s) {pids}. "
            "Use --replace to stop the existing local model server before starting a new one."
        )

    run_dir = _server_profile_dir(root, server_profile.profile_id)
    stop_result: dict[str, Any] | None = None
    if existing and replace:
        stop_result = stop_local_model_servers(
            root,
            dry_run=dry_run,
            timeout_seconds=15.0,
            process_lister=lambda: existing,
            kill_func=kill_func,
            is_process_active=is_process_active,
            sleeper=sleeper,
        )

    payload: dict[str, Any] = {
        "action": "start",
        "status": "would_start" if dry_run else "started",
        "started_at": _utc_now(),
        "profile": server_profile.profile_id,
        "provider": server_profile.provider,
        "model": server_profile.model,
        "base_url": server_profile.base_url,
        "host": server_profile.host,
        "port": server_profile.port,
        "command": list(server_profile.command),
        "replace": replace,
        "dry_run": dry_run,
        "stop_result": stop_result,
        "pid": None,
        "ready": None,
        "log_path": relative_path(root, run_dir / "server.log"),
    }
    if dry_run:
        _write_server_manifest(root, run_dir, payload)
        return payload

    run_dir.mkdir(parents=True, exist_ok=True)
    log_path = run_dir / "server.log"
    log_handle = log_path.open("ab")
    popen = popen_factory or subprocess.Popen
    try:
        process = popen(
            list(server_profile.command),
            stdout=log_handle,
            stderr=log_handle,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
    except FileNotFoundError as exc:
        log_handle.close()
        raise LocalModelServerError(
            f"Cannot start '{server_profile.profile_id}': {server_profile.command[0]} was not found in PATH."
        ) from exc
    except OSError as exc:
        log_handle.close()
        raise LocalModelServerError(f"Cannot start '{server_profile.profile_id}': {exc}") from exc
    finally:
        try:
            log_handle.close()
        except Exception:
            pass

    payload["pid"] = int(getattr(process, "pid", 0) or 0)
    if wait_for_ready:
        payload["ready"] = wait_for_local_model_server(server_profile.base_url, timeout_seconds=ready_timeout_seconds)
        if payload["ready"] is False:
            payload["status"] = "started_unready"
    else:
        payload["ready"] = None
    payload["completed_at"] = _utc_now()
    _write_server_manifest(root, run_dir, payload)
    return payload


def restart_local_model_server(
    root: Path,
    profile: str = "qwen35-mtp",
    **kwargs: Any,
) -> dict[str, Any]:
    kwargs["replace"] = True
    return start_local_model_server(root, profile, **kwargs)


def ensure_local_model_server_for_profile(
    root: Path,
    *,
    provider: str,
    model: str,
    base_url: str | None = None,
    dry_run: bool = False,
    wait_for_ready: bool = True,
    process_lister: ProcessLister | None = None,
    start_profile: StartProfile | None = None,
) -> dict[str, Any]:
    """Ensure the resident local server matches a managed local model profile."""

    target = _managed_profile_for_model(provider=provider, model=model, base_url=base_url)
    if target is None:
        return {
            "action": "ensure",
            "status": "unmanaged",
            "will_manage_local_server": False,
            "provider": provider,
            "model": model,
            "base_url": base_url,
            "reason": "no managed local model server profile matches this provider/model",
        }

    lister = process_lister or (lambda: list_local_model_server_processes(include_ollama=False))
    processes = _filter_processes(lister(), include_ollama=False)
    matching = next(
        (
            process
            for process in processes
            if process.provider == target.provider
            and process.model == target.model
            and (process.port is None or process.port == target.port)
        ),
        None,
    )
    if matching is not None:
        return {
            "action": "ensure",
            "status": "already_running",
            "will_manage_local_server": True,
            "profile": target.profile_id,
            "provider": target.provider,
            "model": target.model,
            "base_url": target.base_url,
            "pid": matching.pid,
            "port": matching.port,
            "reason": "matching managed local model server is already running",
        }

    starter = start_profile or start_local_model_server
    result = starter(
        root,
        target.profile_id,
        host=target.host,
        port=target.port,
        replace=True,
        dry_run=dry_run,
        wait_for_ready=wait_for_ready,
        process_lister=lister,
    )
    result["action"] = "ensure"
    result["will_manage_local_server"] = True
    result["reason"] = "managed local model server was absent or mismatched"
    return result


def wait_for_local_model_server(base_url: str, *, timeout_seconds: float = 60.0) -> bool:
    models_url = base_url.rstrip("/") + "/models"
    deadline = time.monotonic() + max(timeout_seconds, 0)
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(models_url, timeout=2) as response:
                if 200 <= int(getattr(response, "status", 0)) < 300:
                    return True
        except (urllib.error.URLError, OSError, TimeoutError):
            pass
        time.sleep(1.0)
    return False


def render_local_model_server_lines(payload: dict[str, Any]) -> list[str]:
    action = payload.get("action")
    if action == "status" or "processes" in payload and "managed_profiles" in payload:
        lines = [
            f"status: {payload.get('status', 'unknown')}",
            f"running_count: {payload.get('running_count', 0)}",
        ]
        for process in payload.get("processes", []):
            model = process.get("model") or process.get("alias") or "unknown"
            provider = process.get("provider") or process.get("kind") or "unknown"
            rss = process.get("rss_kb")
            rss_text = f", rss_mb={int(rss) // 1024}" if isinstance(rss, int) else ""
            lines.append(
                f"- pid={process.get('pid')} {provider}/{model} "
                f"port={process.get('port', 'unknown')} kind={process.get('kind')}{rss_text}"
            )
        return lines
    if action == "stop":
        return [
            f"status: {payload.get('status', 'unknown')}",
            f"stopped_pids: {', '.join(str(pid) for pid in payload.get('stopped_pids', [])) or 'none'}",
            f"escalated_pids: {', '.join(str(pid) for pid in payload.get('escalated_pids', [])) or 'none'}",
        ]
    if action == "start":
        return [
            f"status: {payload.get('status', 'unknown')}",
            f"profile: {payload.get('profile')}",
            f"model: {payload.get('provider')}/{payload.get('model')}",
            f"pid: {payload.get('pid') or 'not-started'}",
            f"base_url: {payload.get('base_url')}",
            f"log: {payload.get('log_path')}",
        ]
    return [json.dumps(payload, sort_keys=True)]


def _parse_ps_line(raw_line: str) -> tuple[int, int | None, str, int | None, str] | None:
    line = raw_line.strip()
    if not line:
        return None
    parts = line.split(None, 4)
    if len(parts) < 5:
        return None
    try:
        pid = int(parts[0])
    except ValueError:
        return None
    try:
        ppid: int | None = int(parts[1])
    except ValueError:
        ppid = None
    stat = parts[2]
    try:
        rss_kb: int | None = int(parts[3])
    except ValueError:
        rss_kb = None
    return pid, ppid, stat, rss_kb, parts[4]


def _classify_local_model_process(
    *,
    pid: int,
    ppid: int | None,
    stat: str,
    rss_kb: int | None,
    command: str,
) -> LocalModelServerProcess | None:
    lower_command = command.lower()
    if "llama-server" in lower_command:
        tokens = _split_command(command)
        alias = _arg_after(tokens, "--alias")
        port = _safe_int(_arg_after(tokens, "--port"))
        provider = "qwen35-mtp" if alias == "qwen35-9b-mtp" else None
        model = alias or _arg_after(tokens, "--model") or _arg_after(tokens, "--hf-repo")
        return LocalModelServerProcess(
            pid=pid,
            ppid=ppid,
            stat=stat,
            rss_kb=rss_kb,
            command=command,
            kind="llama-server",
            provider=provider,
            model=model,
            alias=alias,
            port=port,
            managed_by_default=True,
        )
    if "ollama serve" in lower_command or "ollama.app" in lower_command:
        return LocalModelServerProcess(
            pid=pid,
            ppid=ppid,
            stat=stat,
            rss_kb=rss_kb,
            command=command,
            kind="ollama",
            provider="local",
            model=None,
            alias=None,
            port=11434,
            managed_by_default=False,
        )
    return None


def _split_command(command: str) -> list[str]:
    try:
        return shlex.split(command)
    except ValueError:
        return command.split()


def _arg_after(tokens: list[str], name: str) -> str | None:
    try:
        index = tokens.index(name)
    except ValueError:
        return None
    next_index = index + 1
    if next_index >= len(tokens):
        return None
    return tokens[next_index]


def _safe_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _filter_processes(
    processes: list[LocalModelServerProcess],
    *,
    profile: str | None = None,
    include_ollama: bool = False,
) -> list[LocalModelServerProcess]:
    filtered = [
        process
        for process in processes
        if process.managed_by_default or (include_ollama and process.kind == "ollama")
    ]
    if not profile:
        return filtered
    resolved = resolve_local_model_server_profile(profile)
    return [
        process
        for process in filtered
        if process.provider == resolved.provider or process.model == resolved.model or process.alias == resolved.model
    ]


def _process_is_active(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _managed_profile_for_model(
    *,
    provider: str,
    model: str,
    base_url: str | None,
) -> LocalModelServerProfile | None:
    if provider != "qwen35-mtp" or model != "qwen35-9b-mtp":
        return None
    host, port = _host_port_from_base_url(base_url, default_host="127.0.0.1", default_port=8080)
    return qwen35_mtp_profile(host=host, port=port)


def _host_port_from_base_url(
    base_url: str | None,
    *,
    default_host: str,
    default_port: int,
) -> tuple[str, int]:
    if not base_url:
        return default_host, default_port
    try:
        parsed = urlparse(base_url)
    except ValueError:
        return default_host, default_port
    return parsed.hostname or default_host, parsed.port or default_port


def _server_profile_dir(root: Path, profile: str) -> Path:
    safe = "".join(ch if ch.isalnum() or ch in ("-", "_", ".") else "-" for ch in profile)
    return devflow_dir(root) / "local-model-servers" / safe


def _write_server_manifest(root: Path, run_dir: Path, payload: dict[str, Any]) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = run_dir / "server.json"
    payload["manifest_path"] = relative_path(root, manifest_path)
    manifest_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


__all__ = [
    "LocalModelServerError",
    "LocalModelServerProcess",
    "LocalModelServerProfile",
    "known_local_model_server_profiles",
    "ensure_local_model_server_for_profile",
    "list_local_model_server_processes",
    "local_model_server_status",
    "parse_local_model_server_processes",
    "qwen35_mtp_profile",
    "render_local_model_server_lines",
    "resolve_local_model_server_profile",
    "restart_local_model_server",
    "start_local_model_server",
    "stop_local_model_servers",
    "wait_for_local_model_server",
]
