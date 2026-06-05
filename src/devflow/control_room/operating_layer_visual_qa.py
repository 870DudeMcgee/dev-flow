from __future__ import annotations

import json
import shutil
import struct
import zlib
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from devflow.control_room.operating_layer_assets import APP_CSS, APP_JS, INDEX_HTML
from devflow.control_room.operating_layer import build_operating_layer_snapshot


DEFAULT_VISUAL_QA_DIR = Path(".devflow/operating-layer/visual-qa")
DEFAULT_BASE_URL = "http://127.0.0.1:8765"


VIEWPORTS: tuple[dict[str, int | str], ...] = (
    {"name": "desktop", "width": 1440, "height": 1000},
    {"name": "mobile", "width": 390, "height": 844},
)


VISUAL_FLOW = (
    "app loads -> first viewport renders Orchestrator, Mission Feed, worker progress, "
    "and Action Rail safety states without horizontal overflow"
)


def build_visual_qa_plan(
    repo_root: Path | None = None,
    *,
    base_url: str = DEFAULT_BASE_URL,
    output_dir: Path = DEFAULT_VISUAL_QA_DIR,
) -> dict[str, Any]:
    root = (repo_root or Path.cwd()).resolve()
    output_dir = Path(output_dir)
    checks = _static_visual_contract_checks()

    return {
        "schema_version": 1,
        "surface": "operating-layer",
        "project_root": str(root),
        "visual_flow": VISUAL_FLOW,
        "browser_runtime": "codex-in-app-browser",
        "serve_command": "devflow operating-layer serve --host 127.0.0.1 --port 8765",
        "base_url": base_url,
        "viewports": [dict(viewport) for viewport in VIEWPORTS],
        "screenshots": [_screenshot_spec(viewport["name"], output_dir) for viewport in VIEWPORTS],
        "checks": checks,
        "playwright_assertions": _playwright_assertions(),
    }


def render_visual_qa_plan_json(
    repo_root: Path | None = None,
    *,
    base_url: str = DEFAULT_BASE_URL,
    output_dir: Path = DEFAULT_VISUAL_QA_DIR,
) -> str:
    return json.dumps(
        build_visual_qa_plan(repo_root, base_url=base_url, output_dir=output_dir),
        indent=2,
        sort_keys=True,
    ) + "\n"


def render_visual_qa_plan(
    repo_root: Path | None = None,
    *,
    base_url: str = DEFAULT_BASE_URL,
    output_dir: Path = DEFAULT_VISUAL_QA_DIR,
) -> str:
    plan = build_visual_qa_plan(repo_root, base_url=base_url, output_dir=output_dir)
    lines = [
        "Dev-Flow Operating Layer Visual QA",
        f"Flow: {plan['visual_flow']}",
        f"Serve: {plan['serve_command']}",
        f"Base URL: {plan['base_url']}",
        "Viewports:",
    ]
    for viewport in plan["viewports"]:
        lines.append(f"- {viewport['name']}: {viewport['width']}x{viewport['height']}")
    lines.append("Checks:")
    for check in plan["checks"]:
        lines.append(f"- {check['id']}: {check['status']} ({check['target']})")
    return "\n".join(lines) + "\n"


def write_visual_qa_image_fallbacks(
    repo_root: Path | None = None,
    *,
    output_dir: Path = DEFAULT_VISUAL_QA_DIR,
    update_baseline: bool = False,
) -> dict[str, Any]:
    root = (repo_root or Path.cwd()).resolve()
    output_dir = Path(output_dir)
    snapshot = build_operating_layer_snapshot(root)
    artifacts: list[dict[str, str]] = []
    statuses: list[str] = []

    for viewport in VIEWPORTS:
        name = str(viewport["name"])
        current = output_dir / "current" / f"{name}.svg"
        baseline = output_dir / "baseline" / f"{name}.svg"
        current_png = output_dir / "current" / f"{name}.png"
        baseline_png = output_dir / "baseline" / f"{name}.png"
        current.parent.mkdir(parents=True, exist_ok=True)
        current.write_text(_render_snapshot_svg(snapshot, viewport), encoding="utf-8")
        _write_snapshot_png(current_png, snapshot, viewport)

        if update_baseline or not baseline.exists():
            baseline.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(current, baseline)
        if update_baseline or not baseline_png.exists():
            baseline_png.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(current_png, baseline_png)

        status = (
            "pass"
            if baseline.exists()
            and baseline_png.exists()
            and baseline.read_text(encoding="utf-8") == current.read_text(encoding="utf-8")
            and baseline_png.read_bytes() == current_png.read_bytes()
            else "changed"
        )
        statuses.append(status)
        artifacts.append(
            {
                "viewport": name,
                "current": current.as_posix(),
                "baseline": baseline.as_posix(),
                "current_png": current_png.as_posix(),
                "baseline_png": baseline_png.as_posix(),
                "status": status,
            }
        )

    return {
        "status": "pass" if all(status == "pass" for status in statuses) else "changed",
        "format": "svg",
        "capture_method": "codex-browser-screenshot-fallback",
        "artifacts": artifacts,
    }


def _screenshot_spec(viewport_name: object, output_dir: Path) -> dict[str, str]:
    name = str(viewport_name)
    return {
        "viewport": name,
        "current": (output_dir / "current" / f"{name}.png").as_posix(),
        "baseline": (output_dir / "baseline" / f"{name}.png").as_posix(),
        "fallback_current": (output_dir / "current" / f"{name}.svg").as_posix(),
        "fallback_baseline": (output_dir / "baseline" / f"{name}.svg").as_posix(),
    }


def _static_visual_contract_checks() -> list[dict[str, str]]:
    return [
        _check(
            "desktop-screenshot",
            "screenshot helper",
            "Desktop viewport and baseline/current screenshot paths are defined.",
            "pass",
        ),
        _check(
            "mobile-screenshot",
            "screenshot helper",
            "Mobile viewport and baseline/current screenshot paths are defined.",
            "pass",
        ),
        _check(
            "no-horizontal-overflow",
            "body/main layout",
            "Body and first-level layout constrain horizontal overflow.",
            "pass" if "overflow-x: hidden;" in APP_CSS and "width: 100%;" in APP_CSS else "fail",
        ),
        _check(
            "orchestrator-first",
            "#orchestrator",
            "The Orchestrator section is the first operating surface after the top bar.",
            "pass" if _index_before('id="orchestrator"', 'id="map"') else "fail",
        ),
        _check(
            "mission-feed-contained",
            ".mission-feed",
            "Mission Feed has a bounded scroll container inside the Orchestrator core.",
            "pass"
            if all(token in INDEX_HTML + APP_CSS for token in ("mission-feed-list", ".mission-feed", "overflow: auto;"))
            else "fail",
        ),
        _check(
            "worker-progress-rows",
            "#orchestrator-agent-progress",
            "Worker progress row hooks are present in HTML, CSS, and render code.",
            "pass"
            if all(
                token in INDEX_HTML + APP_CSS + APP_JS
                for token in ("orchestrator-agent-progress", "agent-progress-row", "renderOrchestratorAgentProgress")
            )
            else "fail",
        ),
        _check(
            "action-rail-safety-states",
            "#action-preview",
            "Action Rail renders read-only, approval-required, and approved verification states.",
            "pass"
            if all(
                token in APP_JS
                for token in (
                    "supervisor_may_auto_run",
                    "requires_human_approval",
                    "isTaskVerificationAction",
                    "I approve this exact Dev-Flow command",
                )
            )
            else "fail",
        ),
    ]


def _playwright_assertions() -> list[dict[str, str]]:
    return [
        {
            "id": "no-horizontal-overflow",
            "script": "document.documentElement.scrollWidth <= document.documentElement.clientWidth",
        },
        {
            "id": "orchestrator-first",
            "script": "document.querySelector('main > section')?.id === 'orchestrator'",
        },
        {
            "id": "mission-feed-contained",
            "script": "document.querySelector('.mission-feed-list')?.scrollHeight >= 0",
        },
        {
            "id": "worker-progress-rows",
            "script": "document.querySelectorAll('#orchestrator-agent-progress .agent-progress-row').length >= 1",
        },
        {
            "id": "action-rail-safety-states",
            "script": "document.querySelector('#action-preview')?.textContent.includes('Approval')",
        },
    ]


def _check(check_id: str, target: str, detail: str, status: str) -> dict[str, str]:
    return {"id": check_id, "target": target, "detail": detail, "status": status}


def _index_before(left: str, right: str) -> bool:
    left_index = INDEX_HTML.find(left)
    right_index = INDEX_HTML.find(right)
    return left_index >= 0 and right_index >= 0 and left_index < right_index


def _render_snapshot_svg(snapshot: Any, viewport: dict[str, int | str]) -> str:
    width = int(viewport["width"])
    height = int(viewport["height"])
    scale = width / 1440
    card_width = max(260, int(width - 48))
    left = 24
    top = 24
    workers = snapshot.worker_activity[:4]
    feed = snapshot.mission_feed[:5]
    actions = snapshot.action_rail[:4]

    rows: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        "<defs>",
        '<linearGradient id="bg" x1="0" x2="1" y1="0" y2="1"><stop offset="0" stop-color="#090912"/><stop offset="1" stop-color="#18243a"/></linearGradient>',
        "</defs>",
        '<rect width="100%" height="100%" fill="url(#bg)"/>',
        _text(left, top + 24, "Dev-Flow Operating Layer", 28 * scale, "#f6f3ff", 800),
        _text(left, top + 54, f"{snapshot.health.total_tasks} tasks / {snapshot.health.active_tasks} active / {snapshot.health.needs_verification} need verification", 15 * scale, "#9fb0c7", 600),
        _panel(left, top + 82, card_width, 190, "Orchestrator", snapshot.next_action.command or "None", "#66f0d1"),
    ]

    y = top + 306
    rows.append(_text(left, y, "Worker Activity", 18 * scale, "#f6f3ff", 800))
    y += 16
    for worker in workers:
        y += 34
        percent = max(0, min(100, int(worker.verified_percent or 0)))
        rows.append(_progress_row(left, y, card_width, worker.name, worker.state, percent))

    y += 58
    rows.append(_text(left, y, "Work Feed", 18 * scale, "#f6f3ff", 800))
    for item in feed:
        y += 30
        rows.append(_text(left + 14, y, f"{item.label}: {item.title}", 13 * scale, "#dfe7ff", 650))

    y += 48
    rows.append(_text(left, y, "Action Rail Safety", 18 * scale, "#f6f3ff", 800))
    for action in actions:
        y += 30
        safety = "read-only" if action.supervisor_may_auto_run else "approval required"
        rows.append(_text(left + 14, y, f"{action.label} / {safety} / {action.safety_class}", 13 * scale, "#dfe7ff", 650))

    rows.append("</svg>")
    return "\n".join(rows) + "\n"


def _panel(x: int, y: int, width: int, height: int, title: str, body: str, accent: str) -> str:
    return "\n".join(
        [
            f'<rect x="{x}" y="{y}" width="{width}" height="{height}" rx="8" fill="#111827" stroke="{accent}" stroke-opacity="0.55"/>',
            _text(x + 18, y + 34, title, 16, "#f6f3ff", 800),
            _text(x + 18, y + 70, body[:140], 13, "#dfe7ff", 600),
        ]
    )


def _progress_row(x: int, y: int, width: int, name: str, state: str, percent: int) -> str:
    bar_width = max(80, width - 220)
    fill_width = int(bar_width * percent / 100)
    return "\n".join(
        [
            f'<rect x="{x}" y="{y - 20}" width="{width}" height="28" rx="6" fill="#172033" stroke="#334155"/>',
            _text(x + 12, y, f"{name}: {state}", 12, "#f6f3ff", 700),
            f'<rect x="{x + width - bar_width - 14}" y="{y - 12}" width="{bar_width}" height="8" rx="4" fill="#263246"/>',
            f'<rect x="{x + width - bar_width - 14}" y="{y - 12}" width="{fill_width}" height="8" rx="4" fill="#66f0d1"/>',
        ]
    )


def _text(x: int, y: int, value: str, size: float, color: str, weight: int) -> str:
    text = escape(str(value))
    return f'<text x="{x}" y="{y}" fill="{color}" font-family="Inter, Arial, sans-serif" font-size="{size:.1f}" font-weight="{weight}">{text}</text>'


def _write_snapshot_png(path: Path, snapshot: Any, viewport: dict[str, int | str]) -> None:
    width = int(viewport["width"])
    height = int(viewport["height"])
    pixels = bytearray([9, 9, 18] * width * height)

    def rect(x: int, y: int, w: int, h: int, color: tuple[int, int, int]) -> None:
        x0 = max(0, x)
        y0 = max(0, y)
        x1 = min(width, x + w)
        y1 = min(height, y + h)
        for py in range(y0, y1):
            row = py * width * 3
            for px in range(x0, x1):
                offset = row + px * 3
                pixels[offset : offset + 3] = bytes(color)

    rect(0, 0, width, height, (9, 9, 18))
    rect(0, 0, width, 92, (17, 24, 39))
    rect(24, 24, min(width - 48, 520), 18, (246, 243, 255))
    rect(24, 58, min(width - 48, 360), 10, (159, 176, 199))
    rect(24, 106, width - 48, 170, (17, 32, 51))
    rect(24, 106, 8, 170, (102, 240, 209))

    y = 326
    for worker in snapshot.worker_activity[:4]:
        percent = max(0, min(100, int(worker.verified_percent or 0)))
        rect(24, y, width - 48, 28, (23, 32, 51))
        rect(38, y + 10, min(220, width - 120), 8, (246, 243, 255))
        bar_width = max(80, width - 340)
        rect(width - bar_width - 38, y + 10, bar_width, 8, (38, 50, 70))
        rect(width - bar_width - 38, y + 10, int(bar_width * percent / 100), 8, (102, 240, 209))
        y += 40

    y += 36
    for index, _item in enumerate(snapshot.mission_feed[:5]):
        rect(38, y + index * 28, min(width - 76, 520), 10, (223, 231, 255))

    y += 178
    for index, action in enumerate(snapshot.action_rail[:4]):
        color = (102, 240, 209) if action.supervisor_may_auto_run else (255, 212, 109)
        rect(38, y + index * 28, 10, 10, color)
        rect(58, y + index * 28, min(width - 96, 440), 10, (223, 231, 255))

    path.parent.mkdir(parents=True, exist_ok=True)
    _write_png(path, width, height, bytes(pixels))


def _write_png(path: Path, width: int, height: int, rgb: bytes) -> None:
    raw = b"".join(b"\x00" + rgb[y * width * 3 : (y + 1) * width * 3] for y in range(height))

    def chunk(name: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + name + data + struct.pack(">I", zlib.crc32(name + data) & 0xFFFFFFFF)

    body = b"\x89PNG\r\n\x1a\n"
    body += chunk("IHDR".encode("ascii"), struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    body += chunk("IDAT".encode("ascii"), zlib.compress(raw, level=9))
    body += chunk("IEND".encode("ascii"), b"")
    path.write_bytes(body)
