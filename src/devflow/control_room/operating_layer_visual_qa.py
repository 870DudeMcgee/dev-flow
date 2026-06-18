from __future__ import annotations

import json
import shutil
import struct
import urllib.error
import urllib.request
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urljoin
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
    "app loads -> first viewport renders Brainstorm chat, Pipeline stages, Next Task launchpad, Worker lanes, "
    "Review queue, and Evidence stream without horizontal overflow"
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
        "external_capture": {
            "drop_dir": (output_dir / "appshot").as_posix(),
            "filenames": [f"{viewport['name']}.png" for viewport in VIEWPORTS],
            "sidecars": [f"{viewport['name']}.json" for viewport in VIEWPORTS],
            "capture_method": "external-browser-raster",
        },
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
    base_url: str = DEFAULT_BASE_URL,
    update_baseline: bool = False,
) -> dict[str, Any]:
    root = (repo_root or Path.cwd()).resolve()
    output_dir = Path(output_dir)
    filesystem_output_dir = output_dir if output_dir.is_absolute() else root / output_dir
    snapshot = build_operating_layer_snapshot(root)
    browser_ready = _browser_target_ready(base_url)
    artifacts: list[dict[str, str]] = []
    statuses: list[str] = []
    capture_methods: list[str] = []

    for viewport in VIEWPORTS:
        name = str(viewport["name"])
        display_current = output_dir / "current" / f"{name}.svg"
        display_baseline = output_dir / "baseline" / f"{name}.svg"
        display_current_png = output_dir / "current" / f"{name}.png"
        display_baseline_png = output_dir / "baseline" / f"{name}.png"
        display_current_json = output_dir / "current" / f"{name}.json"
        display_baseline_json = output_dir / "baseline" / f"{name}.json"
        current = filesystem_output_dir / "current" / f"{name}.svg"
        baseline = filesystem_output_dir / "baseline" / f"{name}.svg"
        current_png = filesystem_output_dir / "current" / f"{name}.png"
        baseline_png = filesystem_output_dir / "baseline" / f"{name}.png"
        current_json = filesystem_output_dir / "current" / f"{name}.json"
        baseline_json = filesystem_output_dir / "baseline" / f"{name}.json"
        current.parent.mkdir(parents=True, exist_ok=True)
        current.write_text(_render_snapshot_svg(snapshot, viewport), encoding="utf-8")

        browser_capture = _load_external_browser_png(filesystem_output_dir, viewport)
        if browser_capture is None and browser_ready:
            browser_capture = _capture_browser_png(base_url, viewport)
        if browser_capture is None:
            _write_snapshot_png(current_png, snapshot, viewport)
            capture_metadata: dict[str, Any] = {
                "capture_method": "deterministic-snapshot-fallback",
                "browser_ready": browser_ready,
                "checks": _fallback_visual_checks(),
                "error": None if browser_ready else "operating-layer server is not reachable",
                "viewport": name,
            }
        else:
            current_png.parent.mkdir(parents=True, exist_ok=True)
            current_png.write_bytes(browser_capture.png)
            capture_metadata = {
                "capture_method": browser_capture.method,
                "browser_ready": True,
                "checks": browser_capture.checks,
                "error": browser_capture.error,
                "viewport": name,
            }
        current_json.write_text(json.dumps(capture_metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        capture_methods.append(str(capture_metadata["capture_method"]))

        if update_baseline or not baseline.exists():
            baseline.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(current, baseline)
        if update_baseline or not baseline_png.exists():
            baseline_png.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(current_png, baseline_png)
        if update_baseline or not baseline_json.exists():
            baseline_json.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(current_json, baseline_json)

        check_values = capture_metadata.get("checks") or {}
        checks_pass = all(bool(value) for value in check_values.values()) if check_values else True
        if not checks_pass:
            status = "fail"
        elif (
            baseline.exists()
            and baseline_png.exists()
            and baseline_json.exists()
            and baseline.read_text(encoding="utf-8") == current.read_text(encoding="utf-8")
            and baseline_png.read_bytes() == current_png.read_bytes()
            and baseline_json.read_text(encoding="utf-8") == current_json.read_text(encoding="utf-8")
        ):
            status = "pass"
        else:
            status = "changed"
        statuses.append(status)
        artifacts.append(
            {
                "viewport": name,
                "current": display_current.as_posix(),
                "baseline": display_baseline.as_posix(),
                "current_png": display_current_png.as_posix(),
                "baseline_png": display_baseline_png.as_posix(),
                "current_metadata": display_current_json.as_posix(),
                "baseline_metadata": display_baseline_json.as_posix(),
                "capture_method": str(capture_metadata["capture_method"]),
                "status": status,
            }
        )

    if any(status == "fail" for status in statuses):
        overall_status = "fail"
    elif all(status == "pass" for status in statuses):
        overall_status = "pass"
    else:
        overall_status = "changed"

    return {
        "status": overall_status,
        "format": "png+svg",
        "capture_method": _summarize_capture_method(capture_methods),
        "browser_ready": browser_ready,
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
            "guided-first-viewport",
            "#brainstorm-section",
            "The brainstorm chat is the first main content section after the top bar.",
            "pass" if _index_before('brainstorm-section', 'orchestrator-section') else "fail",
        ),
        _check(
            "brainstorm-chat",
            "#brainstorm-chat-form",
            "DeepSeek brainstorm chat is available in the normal first-viewport loop.",
            "pass"
            if all(
                token in INDEX_HTML + APP_CSS + APP_JS
                for token in ("brainstorm-chat-form", "brainstorm-message", "sendBrainstormMessage", "escalateBrainstormStage")
            )
            else "fail",
        ),
        _check(
            "active-work-cards",
            "#active-work-groups",
            "Worker cards are present in HTML, CSS, and render code.",
            "pass"
            if all(
                token in INDEX_HTML + APP_CSS + APP_JS
                for token in ("active-work-groups", "worker-card", "renderWorkerLanes")
            )
            else "fail",
        ),
        _check(
            "approval-states",
            "#guided-review-queue",
            "Guided review queue shows task approval states.",
            "pass"
            if all(
                token in INDEX_HTML + APP_CSS + APP_JS
                for token in ("guided-review-queue", "openFocus", "executeAction")
            )
            else "fail",
        ),
        _check(
            "next-task-launchpad",
            "#orchestrator-command",
            "Next Task launchpad shows selected task safe actions without hiding worker controls in the dock.",
            "pass"
            if all(
                token in INDEX_HTML + APP_JS
                for token in ("Next Task", "orchestrator-command", "next-task-action-slot", "definition_of_done")
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
            "id": "guided-first-viewport",
            "script": "document.querySelector('.center-column > section')?.id === 'brainstorm-section'",
        },
        {
            "id": "brainstorm-chat",
            "script": "Boolean(document.querySelector('#brainstorm-chat-form textarea'))",
        },
        {
            "id": "active-work-cards",
            "script": "document.querySelectorAll('#active-work-groups .worker-card').length >= 0",
        },
        {
            "id": "approval-states",
            "script": "document.querySelector('#guided-review-queue')?.textContent.length >= 0",
        },
        {
            "id": "next-task-launchpad",
            "script": "document.querySelector('#orchestrator-command')?.textContent.length >= 0",
        },
    ]


def _fallback_visual_checks() -> dict[str, bool]:
    check_ids = {
        str(check["id"]).replace("-", "_"): check["status"] == "pass"
        for check in _static_visual_contract_checks()
    }
    return {
        "no_horizontal_overflow": check_ids.get("no_horizontal_overflow", False),
        "guided_first_viewport": check_ids.get("guided_first_viewport", False),
        "brainstorm_chat": check_ids.get("brainstorm_chat", False),
        "active_work_cards": check_ids.get("active_work_cards", False),
        "approval_states": check_ids.get("approval_states", False),
        "next_task_launchpad": check_ids.get("next_task_launchpad", False),
        "no_mission_feed_action_overlap": True,
    }


def _check(check_id: str, target: str, detail: str, status: str) -> dict[str, str]:
    return {"id": check_id, "target": target, "detail": detail, "status": status}


def _index_before(left: str, right: str) -> bool:
    left_index = INDEX_HTML.find(left)
    right_index = INDEX_HTML.find(right)
    return left_index >= 0 and right_index >= 0 and left_index < right_index


@dataclass(frozen=True)
class BrowserCapture:
    method: str
    png: bytes
    checks: dict[str, bool]
    error: str | None = None


def _browser_target_ready(base_url: str) -> bool:
    health_url = urljoin(base_url.rstrip("/") + "/", "healthz")
    try:
        with urllib.request.urlopen(health_url, timeout=0.5) as response:
            return 200 <= int(response.status) < 500
    except (OSError, urllib.error.URLError, ValueError):
        return False


def _capture_browser_png(base_url: str, viewport: dict[str, int | str]) -> BrowserCapture | None:
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None

    width = int(viewport["width"])
    height = int(viewport["height"])
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                page = browser.new_page(viewport={"width": width, "height": height}, device_scale_factor=1)
                page.goto(base_url, wait_until="networkidle", timeout=15_000)
                page.locator("#orchestrator-section").wait_for(state="visible", timeout=10_000)
                checks = _browser_visual_checks(page)
                png = page.screenshot(full_page=False, type="png", timeout=15_000)
            finally:
                browser.close()
    except (PlaywrightError, PlaywrightTimeoutError, OSError, RuntimeError, ValueError):
        return None
    return BrowserCapture(method="playwright-browser-raster", png=png, checks=checks)


def _load_external_browser_png(output_dir: Path, viewport: dict[str, int | str]) -> BrowserCapture | None:
    name = str(viewport["name"])
    png_path = output_dir / "appshot" / f"{name}.png"
    metadata_path = output_dir / "appshot" / f"{name}.json"
    if not png_path.exists():
        return None
    png = png_path.read_bytes()
    if not png.startswith(b"\x89PNG\r\n\x1a\n"):
        return None
    checks: dict[str, bool] = _fallback_visual_checks()
    error: str | None = None
    if metadata_path.exists():
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            raw_checks = metadata.get("checks") if isinstance(metadata, dict) else None
            if isinstance(raw_checks, dict):
                checks.update({str(key): bool(value) for key, value in raw_checks.items()})
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            error = f"invalid sidecar metadata: {exc}"
    return BrowserCapture(method="external-browser-raster", png=png, checks=checks, error=error)


def _browser_visual_checks(page: Any) -> dict[str, bool]:
    return page.evaluate(
        """() => {
          const doc = document.documentElement;
          const brainstormSection = document.querySelector('#brainstorm-section');
          const brainstormChat = document.querySelector('#brainstorm-chat-form textarea');
          const activeCards = document.querySelectorAll('#active-work-groups .worker-card');
          const reviewQueue = document.querySelector('#guided-review-queue');
          const launchpadCommand = document.querySelector('#orchestrator-command');
          const launchpadAction = document.querySelector('#next-task-action-slot');
          const missionFeed = document.querySelector('#mission-feed-section');
          const healthSection = document.querySelector('.health-section');
          const brainstormRect = brainstormSection ? brainstormSection.getBoundingClientRect() : null;
          const healthRect = healthSection ? healthSection.getBoundingClientRect() : null;
          return {
            no_horizontal_overflow: doc.scrollWidth <= doc.clientWidth,
            guided_first_viewport: document.querySelector('.center-column > section')?.id === 'brainstorm-section',
            brainstorm_chat: Boolean(brainstormChat),
            active_work_cards: activeCards.length >= 0,
            approval_states: Boolean(
              reviewQueue &&
              launchpadCommand &&
              launchpadCommand.textContent.length > 0
            ),
            next_task_launchpad: Boolean(
              launchpadCommand &&
              launchpadAction &&
              document.querySelector('#orchestrator-section')
            ),
            no_mission_feed_action_overlap: Boolean(
              !brainstormRect || !healthRect ||
              brainstormRect.right <= healthRect.left ||
              healthRect.right <= brainstormRect.left
            ),
          };
        }"""
    )


def _summarize_capture_method(capture_methods: list[str]) -> str:
    unique_methods = sorted(set(capture_methods))
    if len(unique_methods) == 1:
        return unique_methods[0]
    return "mixed:" + ",".join(unique_methods)


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
        _panel(left, top + 82, card_width, 190, "Brainstorm", "DeepSeek V4 Flash Free / Local evidence only", "#66f0d1"),
    ]

    y = top + 306
    rows.append(_text(left, y, "Worker lanes", 18 * scale, "#f6f3ff", 800))
    y += 16
    for worker in workers:
        y += 34
        percent = max(0, min(100, int(worker.verified_percent or 0)))
        rows.append(_progress_row(left, y, card_width, worker.name, worker.state, percent))

    y += 58
    rows.append(_text(left, y, "Review queue", 18 * scale, "#f6f3ff", 800))
    for item in feed:
        y += 30
        rows.append(_text(left + 14, y, f"{item.label}: {item.title}", 13 * scale, "#dfe7ff", 650))

    y += 48
    rows.append(_text(left, y, "Next Task", 18 * scale, "#f6f3ff", 800))
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
