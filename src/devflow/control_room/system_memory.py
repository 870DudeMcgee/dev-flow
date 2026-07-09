"""Small macOS memory-pressure probe for the DevFlow status board."""

from __future__ import annotations

import platform
import re
import subprocess

_BYTES_PER_GIB = 1024**3
_VM_STAT_TIMEOUT_SECONDS = 1.5
_SYSCTL_TIMEOUT_SECONDS = 1.5


def memory_pressure_snapshot() -> dict:
    """Return a compact memory-pressure payload for the browser UI.

    The board only needs an operator signal, not a full Activity Monitor clone.
    macOS does not expose Activity Monitor's exact pressure score as a public
    stable API, so this uses ``vm_stat`` + ``hw.memsize`` to approximate the
    pressure curve and expose the available memory that matters for model
    loading/unloading decisions.
    """
    if platform.system() != "Darwin":
        return {
            "available": False,
            "status": "unsupported",
            "label": "Memory pressure unavailable",
            "reason": "macOS vm_stat is required",
        }

    try:
        vm_stat_text = _run_text(["vm_stat"], timeout=_VM_STAT_TIMEOUT_SECONDS)
        total_bytes = int(_run_text(["sysctl", "-n", "hw.memsize"], timeout=_SYSCTL_TIMEOUT_SECONDS).strip())
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        return {
            "available": False,
            "status": "unknown",
            "label": "Memory pressure unavailable",
            "reason": str(exc),
        }

    page_size = _parse_page_size(vm_stat_text)
    pages = _parse_vm_stat_pages(vm_stat_text)
    total_pages = max(total_bytes // page_size, 1)

    free = pages.get("Pages free", 0)
    speculative = pages.get("Pages speculative", 0)
    purgeable = pages.get("Pages purgeable", 0)
    inactive = pages.get("Pages inactive", 0)
    active = pages.get("Pages active", 0)
    wired = pages.get("Pages wired down", 0)
    compressor = pages.get("Pages occupied by compressor", pages.get("Pages used by compressor", 0))

    # Inactive pages are reusable but not as instantly free as free/speculative
    # pages. Counting half keeps the graph useful for model-load headroom
    # without flickering from ordinary file cache churn.
    reclaimable_pages = free + speculative + purgeable + int(inactive * 0.5)
    used_pressure_pages = max(total_pages - reclaimable_pages, 0)
    pressure = min(1.0, max(0.0, used_pressure_pages / total_pages))
    available_bytes = max(reclaimable_pages * page_size, 0)
    used_bytes = min(total_bytes, max((active + wired + compressor) * page_size, 0))

    if pressure >= 0.86 or available_bytes < 6 * _BYTES_PER_GIB:
        status = "critical"
        label = "High pressure"
    elif pressure >= 0.72 or available_bytes < 12 * _BYTES_PER_GIB:
        status = "warn"
        label = "Watch memory"
    else:
        status = "ok"
        label = "Memory healthy"

    return {
        "available": True,
        "status": status,
        "label": label,
        "pressure": round(pressure, 3),
        "pressure_percent": round(pressure * 100, 1),
        "available_gib": round(available_bytes / _BYTES_PER_GIB, 1),
        "used_gib": round(used_bytes / _BYTES_PER_GIB, 1),
        "total_gib": round(total_bytes / _BYTES_PER_GIB, 1),
    }


def _run_text(command: list[str], *, timeout: float) -> str:
    return subprocess.run(command, check=True, capture_output=True, text=True, timeout=timeout).stdout


def _parse_page_size(vm_stat_text: str) -> int:
    match = re.search(r"page size of (\d+) bytes", vm_stat_text)
    if not match:
        return 4096
    return int(match.group(1))


def _parse_vm_stat_pages(vm_stat_text: str) -> dict[str, int]:
    pages: dict[str, int] = {}
    for line in vm_stat_text.splitlines():
        if ":" not in line:
            continue
        key, raw_value = line.split(":", 1)
        match = re.search(r"(\d+)", raw_value.replace(".", ""))
        if match:
            pages[key.strip().strip('"')] = int(match.group(1))
    return pages
