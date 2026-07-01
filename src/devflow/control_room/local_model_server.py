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

from devflow.control_room.local_model_readiness import (
    ExpectedLocalModelLane,
    LocalModelReadinessError,
    load_expected_local_model_manifest,
)
from devflow.control_room.paths import devflow_dir, relative_path


LocalModelServerKind = Literal["llama-server", "ollama"]
DEFAULT_SERVER_HOST = "127.0.0.1"
DEFAULT_SERVER_PORT = 8080

_MANAGED_SERVER_RECIPES: dict[str, dict[str, str]] = {
    "ornith-9b": {
        "model_path": "~/.hermes/models/gguf/ornith-1.0-9b-q4/ornith-1.0-9b-Q4_K_M.gguf",
        "ctx_size": "131072",
    },
    "ornith-35b": {
        "model_path": "~/.hermes/models/gguf/ornith-1.0-35b-q4/ornith-1.0-35b-Q4_K_M.gguf",
        "ctx_size": "65536",
    },
    "qwen36-27b-q5-mtp": {
        "model_path": "~/.hermes/models/gguf/qwen3.6-27b-mtp-q5/Qwen3.6-27B-Q5_K_M.gguf",
        "ctx_size": "65536",
        "spec_type": "draft-mtp",
        "spec_draft_n_max": "2",
    },
}

class LocalModelServerError(ValueError):
    """Raised when a local model server lifecycle action is unsafe."""


@dataclass(frozen=True)
class LocalModelServerProfile:
    server_id: str
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
            "server_id": self.server_id,
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


def known_local_model_server_profiles(
    *,
    host: str = DEFAULT_SERVER_HOST,
    port: int = DEFAULT_SERVER_PORT,
    binary: str = "llama-server",
) -> dict[str, LocalModelServerProfile]:
    profiles: dict[str, LocalModelServerProfile] = {}
    for profile in _manifest_backed_server_profiles(host=host, port=port, binary=binary):
        profiles[profile.server_id] = profile
    return profiles


def resolve_local_model_server_profile(
    profile: str,
    *,
    host: str = DEFAULT_SERVER_HOST,
    port: int = DEFAULT_SERVER_PORT,
    binary: str = "llama-server",
) -> LocalModelServerProfile:
    canonical_profile = str(profile or "").strip()
    profiles = known_local_model_server_profiles(host=host, port=port, binary=binary)
    try:
        return profiles[canonical_profile]
    except KeyError as exc:
        valid = ", ".join(sorted(profiles))
        raise LocalModelServerError(f"Unknown local model server '{profile}'. Valid servers: {valid}") from exc


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
            if key == profile.server_id
        ],
        "notes": [
            "Default stop/start management targets llama-server processes.",
            "Ollama is shown only with --include-ollama and is not stopped by default.",
        ],
    }


def build_local_model_server_inventory(
    *,
    include_ollama: bool = False,
    process_lister: ProcessLister | None = None,
) -> dict[str, Any]:
    processes = (process_lister or (lambda: list_local_model_server_processes(include_ollama=include_ollama)))()
    profiles = _unique_profiles(known_local_model_server_profiles().values())
    manifest = _load_local_model_manifest_for_inventory()
    rows = [_inventory_profile_row(profile, processes) for profile in profiles]
    rows.extend(
        _inventory_ollama_lane_row(lane, processes)
        for lane in manifest.lanes.values()
        if lane.provider_id == "ollama" and not lane.local_server_backed
    )
    rows.sort(key=lambda row: str(row.get("profile") or ""))
    if include_ollama:
        rows.extend(_inventory_process_row(process) for process in processes if process.kind == "ollama")
    return {"action": "inventory", "profiles": rows}


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
    profile: str,
    *,
    host: str = DEFAULT_SERVER_HOST,
    port: int = DEFAULT_SERVER_PORT,
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

    run_dir = _server_profile_dir(root, server_profile.server_id)
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
        "server": server_profile.server_id,
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
    profile: str,
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
            "server": target.server_id,
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
        target.server_id,
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
            f"server: {payload.get('server') or payload.get('profile')}",
            f"profile: {payload.get('profile')}",
            f"model: {payload.get('provider')}/{payload.get('model')}",
            f"pid: {payload.get('pid') or 'not-started'}",
            f"base_url: {payload.get('base_url')}",
            f"log: {payload.get('log_path')}",
        ]
    return [json.dumps(payload, sort_keys=True)]


def render_local_model_inventory_lines(payload: dict[str, Any]) -> list[str]:
    rows = payload.get("profiles") if isinstance(payload.get("profiles"), list) else []
    columns = [
        ("profile", 22),
        ("server", 18),
        ("provider", 18),
        ("model", 24),
        ("backend/kind", 13),
        ("port", 5),
        ("base_url", 26),
        ("running", 7),
        ("pid", 7),
        ("file_exists", 11),
        ("aliases", 18),
    ]
    rendered_rows: list[dict[str, str]] = []
    widths = {label: len(label) for label, _ in columns}
    for label, minimum in columns:
        widths[label] = max(widths[label], minimum)
    for row in rows:
        aliases = row.get("aliases") if isinstance(row.get("aliases"), list) else []
        rendered = {
            "profile": _display(row.get("profile")),
            "server": _display(row.get("server")),
            "provider": _display(row.get("provider")),
            "model": _display(row.get("model")),
            "backend/kind": _display(row.get("backend_kind")),
            "port": _display(row.get("port")),
            "base_url": _display(row.get("base_url")),
            "running": "yes" if row.get("running") else "no",
            "pid": _display(row.get("pid")),
            "file_exists": _display_bool(row.get("file_exists")),
            "aliases": ",".join(str(item) for item in aliases if item) or "-",
        }
        rendered_rows.append(rendered)
        for label, value in rendered.items():
            widths[label] = max(widths[label], len(value))
    header = " ".join(label.ljust(widths[label]) for label, _ in columns)
    lines = [header, "-" * len(header)]
    for values in rendered_rows:
        lines.append(" ".join(values[label].ljust(widths[label]) for label, _ in columns))
    return lines


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
        model = alias or _arg_after(tokens, "--model") or _arg_after(tokens, "-m")
        matched_profile = _profile_for_llama_process(alias=alias, model=model, port=port)
        provider = matched_profile.provider if matched_profile else None
        model = matched_profile.model if matched_profile else model
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
    host, port = _host_port_from_base_url(base_url, default_host=DEFAULT_SERVER_HOST, default_port=DEFAULT_SERVER_PORT)
    for profile in _unique_profiles(known_local_model_server_profiles(host=host, port=port).values()):
        if profile.provider == provider and profile.model == model:
            return profile
    return None


def _manifest_backed_server_profiles(
    *,
    host: str,
    port: int,
    binary: str,
) -> list[LocalModelServerProfile]:
    try:
        manifest = load_expected_local_model_manifest()
    except LocalModelReadinessError as exc:
        raise LocalModelServerError(f"Could not load local model server profile manifest: {exc}") from exc

    profiles: list[LocalModelServerProfile] = []
    for lane in manifest.lanes.values():
        if not lane.local_server_backed:
            continue
        profile = _profile_from_manifest_lane(lane, host=host, port=port, binary=binary)
        if profile is not None:
            profiles.append(profile)
    return profiles


def _profile_from_manifest_lane(
    lane: ExpectedLocalModelLane,
    *,
    host: str,
    port: int,
    binary: str,
) -> LocalModelServerProfile | None:
    profile_host, profile_port = _lane_server_host_port(lane, host=host, port=port)
    if lane.provider_id in _MANAGED_SERVER_RECIPES:
        return _managed_manifest_profile(lane, host=profile_host, port=profile_port, binary=binary)
    return None


def _managed_manifest_profile(
    lane: ExpectedLocalModelLane,
    *,
    host: str,
    port: int,
    binary: str,
) -> LocalModelServerProfile:
    recipe = _MANAGED_SERVER_RECIPES[lane.provider_id]
    model_path = Path(recipe["model_path"]).expanduser().as_posix()
    command = [
        binary,
        "-m",
        model_path,
        "--alias",
        lane.model_id,
        "--host",
        host,
        "--port",
        str(port),
        "--ctx-size",
        recipe["ctx_size"],
        "--gpu-layers",
        "99",
        "--flash-attn",
        "on",
        "--parallel",
        "1",
        "--jinja",
        "--reasoning",
        "auto",
        "--temp",
        "0.6",
        "--top-p",
        "0.95",
        "--top-k",
        "20",
        "--no-webui",
    ]
    if recipe.get("spec_type"):
        command.extend(["--spec-type", recipe["spec_type"]])
    if recipe.get("spec_draft_n_max"):
        command.extend(["--spec-draft-n-max", recipe["spec_draft_n_max"]])
    return LocalModelServerProfile(
        server_id=lane.provider_id,
        profile_id=lane.profile_id,
        provider=lane.provider_id,
        model=lane.model_id,
        host=host,
        port=port,
        base_url=f"http://{host}:{port}/v1",
        command=command,
        aliases=_dedupe_aliases(lane.lane_id, lane.provider_id, lane.model_id),
    )


def _lane_server_host_port(
    lane: ExpectedLocalModelLane,
    *,
    host: str,
    port: int,
) -> tuple[str, int]:
    manifest_host, manifest_port = _host_port_from_base_url(
        lane.base_url,
        default_host=DEFAULT_SERVER_HOST,
        default_port=lane.port or DEFAULT_SERVER_PORT,
    )
    resolved_host = host if host != DEFAULT_SERVER_HOST else manifest_host
    resolved_port = port if port != DEFAULT_SERVER_PORT else manifest_port
    return resolved_host, resolved_port


def _profile_for_llama_process(
    *,
    alias: str | None,
    model: str | None,
    port: int | None,
) -> LocalModelServerProfile | None:
    for profile in _unique_profiles(known_local_model_server_profiles().values()):
        if port is not None and profile.port != port:
            continue
        identity_values = {profile.model, *profile.aliases}
        if alias in identity_values or model in identity_values:
            return profile
    return None


def _inventory_profile_row(
    profile: LocalModelServerProfile,
    processes: list[LocalModelServerProcess],
) -> dict[str, Any]:
    process = _running_process_for_profile(profile, processes)
    return {
        "profile": profile.profile_id,
        "server": profile.server_id,
        "provider": profile.provider,
        "model": profile.model,
        "backend_kind": "llama-server",
        "port": profile.port,
        "base_url": profile.base_url,
        "running": process is not None,
        "pid": process.pid if process else None,
        "file_exists": _profile_file_exists(profile),
        "aliases": list(profile.aliases),
    }


def _inventory_process_row(process: LocalModelServerProcess) -> dict[str, Any]:
    return {
        "profile": process.alias or process.model or process.kind,
        "server": None,
        "provider": process.provider,
        "model": process.model,
        "backend_kind": process.kind,
        "port": process.port,
        "base_url": f"http://127.0.0.1:{process.port}" if process.port else None,
        "running": True,
        "pid": process.pid,
        "file_exists": None,
        "aliases": [process.alias] if process.alias else [],
    }


def _inventory_ollama_lane_row(
    lane: ExpectedLocalModelLane,
    processes: list[LocalModelServerProcess],
) -> dict[str, Any]:
    process = next((item for item in processes if item.kind == "ollama"), None)
    return {
        "profile": lane.profile_id,
        "server": None,
        "provider": lane.provider_id,
        "model": lane.model_id,
        "backend_kind": "ollama",
        "port": lane.port,
        "base_url": lane.base_url,
        "running": process is not None,
        "pid": process.pid if process else None,
        "file_exists": None,
        "aliases": list(_dedupe_aliases(lane.lane_id, lane.profile_id, lane.model_id)),
    }


def _running_process_for_profile(
    profile: LocalModelServerProfile,
    processes: list[LocalModelServerProcess],
) -> LocalModelServerProcess | None:
    identities = {profile.model, *profile.aliases}
    for process in processes:
        if process.provider == profile.provider and process.model == profile.model:
            return process
        if process.port == profile.port and (process.model in identities or process.alias in identities):
            return process
    return None


def _profile_file_exists(profile: LocalModelServerProfile) -> bool | None:
    model_path = _arg_after(profile.command, "-m")
    if not model_path:
        return None
    return Path(model_path).expanduser().exists()


def _unique_profiles(profiles: Any) -> list[LocalModelServerProfile]:
    unique: dict[str, LocalModelServerProfile] = {}
    for profile in profiles:
        if isinstance(profile, LocalModelServerProfile):
            unique.setdefault(profile.server_id, profile)
    return list(unique.values())


def _load_local_model_manifest_for_inventory() -> Any:
    try:
        return load_expected_local_model_manifest()
    except LocalModelReadinessError as exc:
        raise LocalModelServerError(f"Could not load local model server inventory manifest: {exc}") from exc


def _dedupe_aliases(*aliases: str | None) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []
    for alias in aliases:
        if not alias or alias in seen:
            continue
        seen.add(alias)
        result.append(alias)
    return tuple(result)


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


def _display(value: object) -> str:
    if value is None:
        return "-"
    return str(value)


def _display_bool(value: object) -> str:
    if value is None:
        return "-"
    return "yes" if bool(value) else "no"


__all__ = [
    "LocalModelServerError",
    "LocalModelServerProcess",
    "LocalModelServerProfile",
    "known_local_model_server_profiles",
    "build_local_model_server_inventory",
    "ensure_local_model_server_for_profile",
    "list_local_model_server_processes",
    "local_model_server_status",
    "parse_local_model_server_processes",
    "render_local_model_inventory_lines",
    "render_local_model_server_lines",
    "resolve_local_model_server_profile",
    "restart_local_model_server",
    "start_local_model_server",
    "stop_local_model_servers",
    "wait_for_local_model_server",
]
