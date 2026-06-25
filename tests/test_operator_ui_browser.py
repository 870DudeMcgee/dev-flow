from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from devflow.control_room.persistence import get_task, save_task, utc_now
from devflow.control_room.project_models import ProjectRecord
from devflow.control_room.project_registry import register_project
from devflow.control_room.serial_local_agent_run import create_serial_local_agent_run
from devflow.control_room.worker_evidence import write_worker_evidence
from tests.helpers import init_test_git_repo


pytestmark = pytest.mark.ui_browser

REPO_ROOT = Path(__file__).resolve().parents[1]
PYTHON = Path(sys.executable)
APPROVAL_PHRASE = "I approve this exact Dev-Flow command"


try:
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import Page, expect, sync_playwright
except ModuleNotFoundError:  # pragma: no cover - exercised only in minimal dev envs.
    PlaywrightError = Exception  # type: ignore[assignment]
    Page = Any  # type: ignore[assignment]
    expect = None  # type: ignore[assignment]
    sync_playwright = None  # type: ignore[assignment]


@dataclass(frozen=True)
class ScratchState:
    root: Path
    devflow_home: Path
    project_root: Path
    missing_project: Path


@pytest.fixture()
def scratch_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ScratchState:
    root = tmp_path / "operator-ui"
    root.mkdir()
    init_test_git_repo(root)
    brief = root / "goal.md"
    brief.write_text("# Browser automation goal\n\nShip UI confidence.\n", encoding="utf-8")
    subprocess.run(["git", "add", "goal.md"], cwd=root, capture_output=True, text=True, check=True)
    subprocess.run(["git", "commit", "-m", "add browser goal"], cwd=root, capture_output=True, text=True, check=True)
    devflow_home = tmp_path / "home"
    monkeypatch.setenv("DEVFLOW_HOME", devflow_home.as_posix())

    _run_devflow(root, devflow_home, "init")
    _run_devflow(root, devflow_home, "task", "create", "Browser active work")
    routing_decision = {
        "routing_decision": {
            "selected": {
                "agent_id": "qwen-worker",
                "label": "Hermes Qwen Implementer",
                "provider": "ollama",
                "model": "qwen3.6-32b-256k:latest",
                "reason": "Recommended worker for browser launchpad fixture.",
            },
            "rejected": [
                {
                    "agent_id": "blocked-local-worker",
                    "provider": "ollama",
                    "reason": "Runtime lock is busy.",
                }
            ],
        }
    }
    (root / ".devflow" / "tasks" / "task-0001" / "routing-decision.yaml").write_text(
        json.dumps(routing_decision), encoding="utf-8"
    )
    _run_devflow(root, devflow_home, "task", "create", "Browser promotion candidate")
    _run_devflow(root, devflow_home, "task", "run", "task-0002", "--worker", "shell", "--", "/bin/sh", "-c", "printf ready > approval.txt")
    _run_devflow(root, devflow_home, "task", "verify", "task-0002", "--shell", "test -f approval.txt")
    _run_devflow(root, devflow_home, "task", "promote-preview", "task-0002")

    _run_devflow(root, devflow_home, "task", "create", "Browser blocked question")
    _write_question(root, "task-0003")
    blocked = get_task(root, "task-0003")
    blocked.status = "blocked"
    save_task(root / ".devflow" / "tasks" / blocked.id, blocked)

    _run_devflow(root, devflow_home, "task", "create", "Local model evidence lane")
    write_worker_evidence(
        root=root,
        worker_type="local_model_worker_pool",
        profile_id="local-qwopus-inspector",
        worker_id="local-qwopus-inspector",
        task_id="task-0004",
        run_id="run-1",
        packet_text="packet",
        raw_output="raw local evidence",
        response_text="local evidence response",
        model="qwopus:latest",
        adapter="ollama_chat",
        adapter_maturity="local_patch_runtime",
        permission_mode="read_only",
        hermes_delegable=True,
        runtime="local_model_client",
        status="success",
        started_at="2026-06-16T00:00:00+00:00",
        quality_notes="useful browser fixture",
        quality_score=0.82,
    )

    _run_devflow(root, devflow_home, "loop", "init", "daily", "--template", "goal-autopilot")
    _run_devflow(root, devflow_home, "goal", "init", "G-0001", "--from", str(brief))

    project_root = tmp_path / "registered-project"
    project_root.mkdir()
    init_test_git_repo(project_root)
    _run_devflow(project_root, devflow_home, "init")
    _run_devflow(project_root, devflow_home, "task", "create", "Project scoped browser task")
    missing_project = tmp_path / "missing-project"
    register_project(
        ProjectRecord(
            project_id="demo",
            name="Demo Project",
            path=project_root.as_posix(),
            last_seen_at=utc_now(),
        )
    )
    register_project(
        ProjectRecord(
            project_id="missing",
            name="Missing Project",
            path=missing_project.as_posix(),
            last_seen_at=utc_now(),
        )
    )

    return ScratchState(root=root, devflow_home=devflow_home, project_root=project_root, missing_project=missing_project)


@pytest.fixture()
def operating_layer_url(scratch_state: ScratchState) -> str:
    port = _free_port()
    env = _devflow_env(scratch_state.devflow_home)
    process = subprocess.Popen(
        [
            PYTHON.as_posix(),
            "-m",
            "devflow.cli",
            "operating-layer",
            "serve",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=scratch_state.root,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    base_url = f"http://127.0.0.1:{port}"
    try:
        _wait_for_healthz(base_url, process)
        yield base_url
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


@pytest.fixture()
def browser_page(operating_layer_url: str):
    if sync_playwright is None:
        pytest.skip("Playwright is not installed; install playwright and Chromium to run UI browser tests.")
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch()
        except PlaywrightError as exc:
            pytest.skip(f"Playwright Chromium is unavailable: {exc}")
        page = browser.new_page(viewport={"width": 1440, "height": 980}, device_scale_factor=1)
        console_errors: list[str] = []
        page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)
        page.goto(operating_layer_url, wait_until="domcontentloaded")
        _wait_for_hydration(page)
        yield page, console_errors
        browser.close()


def test_app_loads_assets_snapshot_health_without_console_errors_or_overflow(
    browser_page: tuple[Page, list[str]],
    operating_layer_url: str,
) -> None:
    page, console_errors = browser_page

    health = page.request.get(f"{operating_layer_url}/healthz")
    assert health.ok
    assert health.json()["status"] == "ok"
    snapshot = page.request.get(f"{operating_layer_url}/api/snapshot")
    assert snapshot.ok
    assert snapshot.json()["tasks"][0]["id"] == "task-0001"

    assert "active" in str(page.locator('[data-nav="home"]').get_attribute("class") or "")
    expect(page.get_by_role("link", name="Advanced")).to_be_visible()
    expect(page.get_by_role("heading", name="Brainstorm")).to_be_visible()
    expect(page.get_by_role("heading", name="Pipeline")).to_be_visible()
    expect(page.get_by_role("heading", name="Next Task")).to_be_visible()
    expect(page.get_by_role("heading", name="Worker lanes")).to_be_visible()
    expect(page.get_by_role("heading", name="Review queue")).to_be_visible()
    expect(page.get_by_role("heading", name="Evidence stream")).to_be_visible()
    runtime_panel = page.locator("#serial-runtime-panel")
    expect(runtime_panel).to_be_visible()
    expect(runtime_panel).to_contain_text("Worker Runtime")
    expect(runtime_panel).to_contain_text("No packet yet")
    expect(runtime_panel).to_contain_text("next safe action")
    expect(page.locator("#brainstorm-definition-of-done")).to_be_visible()
    expect(page.locator("#active-work-groups")).to_contain_text("Browser active work")
    expect(page.locator("#guided-review-queue")).to_contain_text("Browser promotion candidate")
    assert _no_horizontal_overflow(page)
    assert console_errors == []


def test_home_prioritizes_brainstorm_workbench_without_closed_history_noise(
    browser_page: tuple[Page, list[str]],
) -> None:
    page, _console_errors = browser_page

    desktop = _home_layout_metrics(page)
    assert desktop["scroll_y"] == 0
    assert desktop["idea_top"] < 220
    assert desktop["idea_top"] < desktop["brainstorm_top"]
    assert desktop["brainstorm_top"] < desktop["pipeline_top"]
    assert desktop["pipeline_top"] < desktop["next_task_top"]
    assert desktop["pipeline_top"] < desktop["viewport_height"]
    assert desktop["next_task_top"] < desktop["viewport_height"]
    assert desktop["active_top"] < desktop["viewport_height"]
    assert desktop["worker_lanes_top"] < desktop["viewport_height"]
    assert desktop["review_queue_top"] < desktop["viewport_height"]
    assert desktop["evidence_stream_top"] < desktop["viewport_height"]
    assert desktop["active_height"] <= desktop["viewport_height"] * 1.35
    assert desktop["closed_guided_cards"] == 0

    page.set_viewport_size({"width": 390, "height": 900})
    mobile = _home_layout_metrics(page)
    assert mobile["scroll_y"] == 0
    assert mobile["idea_top"] < 220
    assert mobile["idea_top"] < mobile["brainstorm_top"]
    assert mobile["brainstorm_top"] < mobile["pipeline_top"]
    assert mobile["pipeline_top"] < mobile["next_task_top"]
    assert mobile["pipeline_top"] < mobile["viewport_height"]
    assert mobile["next_task_top"] < mobile["viewport_height"] * 1.5
    assert mobile["active_height"] <= mobile["viewport_height"] * 1.35
    assert mobile["closed_guided_cards"] == 0
    assert _no_horizontal_overflow(page)


def test_home_exposes_idea_to_task_flow_and_review_dock(browser_page: tuple[Page, list[str]]) -> None:
    page, _console_errors = browser_page
    metrics = page.evaluate(
        """() => {
          const flow = [
            ['idea', '#idea-greenhouse-section'],
            ['brainstorm', '#brainstorm-section'],
            ['pipeline', '#pipeline-spine'],
            ['task', '#orchestrator-section'],
          ];
          const product = document.querySelector('#product-review-section')?.getBoundingClientRect();
          const lanes = ['#active-work-groups', '#guided-review-queue', '#guided-evidence-stream'].map((selector) => {
            const rect = document.querySelector(selector)?.getBoundingClientRect();
            return { selector, top: rect ? Math.round(rect.top) : null };
          });
          return {
            flow: flow.map(([name, selector]) => {
              const element = document.querySelector(selector);
              const rect = element?.getBoundingClientRect();
              return [name, Boolean(element), rect ? Math.round(rect.top) : null];
            }),
            product: { exists: Boolean(product), top: product ? Math.round(product.top) : null },
            lanes,
            viewport_height: Math.round(window.innerHeight),
          };
        }"""
    )
    assert [name for name, exists, _top in metrics["flow"] if exists] == [
        "idea",
        "brainstorm",
        "pipeline",
        "task",
    ]
    tops = [top for _name, exists, top in metrics["flow"] if exists]
    assert tops == sorted(tops)
    assert tops[0] < 160
    assert metrics["product"]["exists"] is True
    assert metrics["product"]["top"] < metrics["viewport_height"]
    assert all(item["top"] is not None and item["top"] < metrics["viewport_height"] for item in metrics["lanes"])


def test_product_stage_contains_task_launchpad_review_and_evidence(browser_page) -> None:
    page, _console_errors = browser_page
    product = page.locator("#product-review-section")
    expect(product).to_be_visible()
    expect(product).to_contain_text("Product / Review")
    expect(product).to_contain_text("Worker lanes")
    expect(product).to_contain_text("Review queue")
    expect(product).to_contain_text("Evidence stream")



def test_idea_greenhouse_lanes_wrap_at_mobile_width(browser_page: tuple[Page, list[str]]) -> None:
    page, _console_errors = browser_page

    page.set_viewport_size({"width": 390, "height": 900})
    expect(page.locator("#idea-greenhouse-lanes")).to_be_visible()
    expect(page.locator("#idea-greenhouse-lanes .idea-lane").first).to_be_visible()
    metrics = page.evaluate(
        """() => {
          const lanes = document.querySelector("#idea-greenhouse-lanes");
          if (!lanes) {
            return { exists: false };
          }
          const laneRects = Array.from(lanes.children).map((element) => element.getBoundingClientRect());
          const lanesRect = lanes.getBoundingClientRect();
          const maxRight = Math.max(lanesRect.right, ...laneRects.map((rect) => rect.right));
          const columns = getComputedStyle(lanes)
            .gridTemplateColumns
            .split(" ")
            .filter((part) => part && part !== "none")
            .length;
          return {
            exists: true,
            lane_count: lanes.children.length,
            column_count: columns,
            max_right: Math.round(maxRight),
            viewport_width: Math.round(window.innerWidth),
            no_horizontal_overflow:
              document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1 &&
              document.body.scrollWidth <= document.body.clientWidth + 1,
          };
        }"""
    )

    assert metrics["exists"] is True
    assert metrics["lane_count"] >= 1
    assert metrics["column_count"] == 1
    assert metrics["max_right"] <= metrics["viewport_width"] + 1
    assert metrics["no_horizontal_overflow"] is True


def test_worker_row_selects_launchpad_and_runs_inline_shell_worker(
    browser_page: tuple[Page, list[str]],
    scratch_state: ScratchState,
) -> None:
    page, _console_errors = browser_page

    page.locator("#active-work-groups .worker-card", has_text="Browser active work").locator("[data-select-task]").first.click()
    expect(page.locator("#orchestrator-goal-title")).to_contain_text("task-0001")
    expect(page.locator("#orchestrator-goal-title")).to_contain_text("Browser active work")
    expect(page.locator("#next-task-meta")).to_contain_text("shell")
    expect(page.locator("#next-task-definition-of-done")).to_contain_text("No definition captured yet.")
    expect(page.locator("#next-task-action-slot")).to_contain_text("Start")
    expect(page.locator("#next-task-shell-panel")).to_be_visible()
    expect(page.locator("#active-work-groups .worker-card.selected")).to_contain_text("Browser active work")

    _open_shell_fallback(page)
    page.locator("#next-task-shell-panel [data-shell-command]").fill("printf launchpad-run > launchpad-run.txt")
    page.locator("#next-task-shell-panel [data-task-run-shell]").click()
    expect(page.locator("#next-task-command-output")).to_contain_text("Exit 0", timeout=15_000)
    assert (scratch_state.root / ".devflow" / "workspaces" / "task-0001" / "launchpad-run.txt").exists()
    assert not (scratch_state.root / "launchpad-run.txt").exists()


def test_first_viewport_action_map_prioritizes_next_operator_levers(
    browser_page: tuple[Page, list[str]],
) -> None:
    page, _console_errors = browser_page

    page.locator("#active-work-groups .worker-card", has_text="Browser active work").locator("[data-select-task]").first.click()
    action_map = page.locator("#operator-next-steps")
    expect(action_map).to_be_visible()
    expect(action_map).to_contain_text("What can I do next")
    expect(action_map.locator('[data-next-step-card="active_task"]')).to_contain_text("Browser active work")
    expect(action_map.locator('[data-next-step-card="recommended_worker"]')).to_contain_text("Hermes Qwen Implementer")
    expect(action_map.locator('[data-next-step-card="serial_runtime"]')).to_contain_text("No packet yet")
    expect(action_map.locator('[data-next-step-card="latest_evidence"]')).to_contain_text("Latest evidence")
    expect(action_map.locator('[data-next-step-card="review_action"]')).to_contain_text("Browser promotion candidate")
    expect(action_map.locator('[data-open-next-worker-card="qwen-worker"]')).to_be_visible()

    metrics = page.evaluate(
        """() => {
          const selectors = [
            '#operator-next-steps [data-next-step-card="active_task"]',
            '#operator-next-steps [data-next-step-card="recommended_worker"]',
            '#operator-next-steps [data-next-step-card="serial_runtime"]',
            '#operator-next-steps [data-next-step-card="latest_evidence"]',
            '#operator-next-steps [data-next-step-card="review_action"]',
          ];
          return Object.fromEntries(selectors.map(selector => {
            const element = document.querySelector(selector);
            const rect = element?.getBoundingClientRect();
            return [selector, Boolean(rect && rect.top >= 0 && rect.top < window.innerHeight)];
          }));
        }"""
    )
    assert all(metrics.values()), metrics

    action_map.locator('[data-open-next-worker-card="qwen-worker"]').click()
    expect(page.locator("#next-task-packet-panel")).to_be_visible()


def test_worker_cards_are_keyboard_accessible_and_copyable(
    browser_page: tuple[Page, list[str]],
) -> None:
    page, _console_errors = browser_page

    page.locator("#active-work-groups .worker-card", has_text="Browser active work").locator("[data-select-task]").first.click()
    panel = page.locator("#next-task-shell-panel")
    ai_card = panel.locator('[data-worker-option-card][data-worker-action-kind="serial_packet"]').first
    blocked_card = panel.locator('[data-worker-option-card][data-worker-id="blocked-local-worker"]').first

    expect(ai_card).to_have_attribute("role", "button")
    expect(ai_card).to_have_attribute("tabindex", "0")
    expect(ai_card).to_have_attribute("aria-disabled", "false")
    expect(ai_card).to_have_attribute("aria-label", re.compile("Hermes Qwen Implementer.*Enter.*Space"))
    expect(blocked_card).to_have_attribute("aria-disabled", "true")
    expect(blocked_card).to_have_attribute("aria-label", re.compile("Runtime lock is busy"))
    expect(blocked_card).to_contain_text("Unavailable")
    expect(blocked_card).to_contain_text("Runtime lock is busy")

    ai_card.focus()
    page.keyboard.press("Enter")
    packet_panel = page.locator("#next-task-packet-panel")
    expect(packet_panel).to_be_visible()
    packet_form = packet_panel.locator('[role="form"]')
    expect(packet_form).to_have_attribute("aria-label", re.compile("Create serial packet.*Hermes Qwen Implementer"))
    expect(packet_panel.locator('[data-packet-allowed-files]')).to_have_attribute(
        "aria-label", "Allowed files for serial packet"
    )
    expect(packet_panel.locator('[data-packet-verify-command]')).to_have_attribute(
        "aria-label", "Verification command for serial packet"
    )

    packet_panel.locator('[data-packet-allowed-files]').fill("src/devflow/control_room/operating_layer_script.py")
    packet_panel.locator('[data-packet-verify-command]').fill("env PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_operator_ui_browser.py -q")
    _install_clipboard_spy(page)
    copy_button = packet_panel.locator('[data-copy-command][data-copy-kind="packet_preview"]')
    expect(copy_button).to_have_attribute("aria-label", "Copy packet command preview")
    copy_button.click()
    expect(copy_button).to_contain_text("Copied")
    copied = page.evaluate("window.__copiedText")
    assert "devflow agent serial-packet" in copied
    assert "<allowed-file>" not in copied
    assert "<verification-command>" not in copied

    page.evaluate(
        """() => {
          const panel = document.querySelector('#next-task-packet-panel');
          panel.hidden = true;
          panel.innerHTML = '';
        }"""
    )
    ai_card.focus()
    page.keyboard.press("Space")
    expect(packet_panel).to_be_visible()


def test_action_buttons_use_semantic_affordance_classes_and_copy_helpers(
    browser_page: tuple[Page, list[str]],
    scratch_state: ScratchState,
) -> None:
    page, _console_errors = browser_page

    page.locator("#active-work-groups .worker-card", has_text="Browser active work").locator("[data-select-task]").first.click()
    panel = page.locator("#next-task-shell-panel")
    _open_shell_fallback(page)
    shell_button = panel.locator('[data-task-run-shell]')
    expect(shell_button).to_have_attribute("data-action-intent", "safe")
    expect(shell_button).to_have_attribute("class", re.compile("btn-primary"))
    expect(shell_button).to_have_attribute("aria-label", re.compile("Run shell command"))

    terminal_copy = panel.locator('.nt-shell-fallback [data-copy-command][data-copy-kind="terminal_command"]')
    expect(terminal_copy).to_be_visible()
    expect(terminal_copy).to_have_attribute("class", re.compile("btn-readonly"))
    expect(terminal_copy).to_have_attribute("aria-label", re.compile("Copy terminal command"))
    _install_clipboard_spy(page)
    terminal_copy.click()
    copied = page.evaluate("window.__copiedText")
    assert copied.startswith("devflow task run task-0001")

    created = _run_devflow(scratch_state.root, scratch_state.devflow_home, "task", "create", "Browser verify polish")
    task_id = next(part.rstrip(":") for part in created.stdout.split() if part.startswith("task-"))
    _run_devflow(scratch_state.root, scratch_state.devflow_home, "task", "run", task_id, "--worker", "shell", "--", "/bin/sh", "-c", "printf verify > verify-polish.txt")
    page.reload(wait_until="domcontentloaded")
    _wait_for_hydration(page)
    page.locator("#active-work-groups .worker-card", has_text="Browser verify polish").locator("[data-select-task]").first.click()
    verify_button = page.locator("#next-task-verify-panel [data-task-verify]")
    expect(verify_button).to_have_attribute("data-action-intent", "verify")
    expect(verify_button).to_have_attribute("class", re.compile("btn-caution"))
    expect(verify_button).to_have_attribute("aria-label", f"Run verification for {task_id}")

    page.locator("#active-work-groups .worker-card", has_text="Browser promotion candidate").locator("[data-select-task]").first.click()
    review_button = page.locator('[data-command^="devflow task promote-preview"]').first
    expect(review_button).to_have_attribute("data-action-intent", "readonly")
    expect(review_button).to_have_attribute("class", re.compile("btn-readonly"))
    promote_button = page.locator('[data-command^="devflow task promote "]').first
    expect(promote_button).to_have_attribute("data-action-intent", "safe")
    expect(promote_button).to_have_attribute("class", re.compile("btn-primary"))


def test_launchpad_renders_worker_options_above_shell_without_direct_hermes_launch(
    browser_page: tuple[Page, list[str]],
) -> None:
    page, _console_errors = browser_page

    page.locator("#active-work-groups .worker-card", has_text="Browser active work").locator("[data-select-task]").first.click()
    panel = page.locator("#next-task-shell-panel")
    expect(panel).to_be_visible()
    ai_card = panel.locator('[data-worker-option-card][data-worker-action-kind="serial_packet"]').first
    expect(ai_card).to_be_visible()
    expect(ai_card).to_contain_text("Recommended worker")
    expect(ai_card).to_contain_text("Hermes Qwen Implementer")
    expect(ai_card).to_contain_text("Creates a bounded serial packet for qwen-worker")
    expect(ai_card).to_contain_text("Launch remains outside browser")
    expect(ai_card).to_contain_text("verifier is final proof")

    packet_command = ai_card.get_attribute("data-worker-command") or ""
    assert packet_command.startswith("devflow agent serial-packet ")
    assert "--runtime hermes-profile" in packet_command
    assert "--hermes-profile qwen-worker" in packet_command
    assert "devflow agent hermes-run" not in packet_command
    assert panel.locator('[data-worker-option-card="shell"]').count() == 0
    _open_shell_fallback(page)
    expect(panel.locator(".nt-shell-fallback [data-task-run-shell]")).to_be_visible()
    assert panel.locator("[data-task-run-shell]").bounding_box()["y"] > ai_card.bounding_box()["y"]


def test_clicking_ai_worker_card_opens_packet_form_without_creating_packet(
    browser_page: tuple[Page, list[str]],
    scratch_state: ScratchState,
) -> None:
    page, _console_errors = browser_page

    page.locator("#active-work-groups .worker-card", has_text="Browser active work").locator("[data-select-task]").first.click()
    panel = page.locator("#next-task-shell-panel")
    expect(panel).to_be_visible()
    packet_panel = page.locator("#next-task-packet-panel")
    expect(packet_panel).to_be_hidden()

    blocked_card = panel.locator('[data-worker-option-card][data-worker-id="blocked-local-worker"]').first
    expect(blocked_card).to_be_visible()
    expect(blocked_card).to_contain_text("Runtime lock is busy")
    blocked_card.click(force=True)
    expect(packet_panel).to_be_hidden()
    expect(page.locator("#next-task-command-output")).to_contain_text("Runtime lock is busy")

    ai_card = panel.locator('[data-worker-option-card][data-worker-action-kind="serial_packet"]').first
    ai_card.click()
    expect(packet_panel).to_be_visible()
    expect(packet_panel).to_contain_text("Create serial packet")
    expect(packet_panel).to_contain_text("Hermes Qwen Implementer")
    expect(packet_panel.locator('[data-packet-allowed-files]')).to_be_visible()
    expect(packet_panel.locator('[data-packet-verify-command]')).to_be_visible()
    expect(packet_panel.locator('[data-packet-command-preview]')).to_contain_text("devflow agent serial-packet")
    expect(packet_panel.locator('[data-create-serial-packet]')).to_be_disabled()
    assert not (scratch_state.root / ".devflow" / "local-agent-runs").exists()


def test_ai_worker_packet_form_creates_serial_packet(
    browser_page: tuple[Page, list[str]],
    scratch_state: ScratchState,
) -> None:
    page, _console_errors = browser_page

    page.locator("#active-work-groups .worker-card", has_text="Browser active work").locator("[data-select-task]").first.click()
    page.locator('[data-worker-option-card][data-worker-action-kind="serial_packet"]').first.click()
    packet_panel = page.locator("#next-task-packet-panel")
    expect(packet_panel).to_be_visible()

    packet_panel.locator('[data-packet-allowed-files]').fill("src/example.py, src/second.py")
    packet_panel.locator('[data-packet-verify-command]').fill("python -m pytest tests/example.py -q")
    expect(packet_panel.locator('[data-create-serial-packet]')).to_be_enabled()
    expect(packet_panel.locator('[data-packet-command-preview]')).to_contain_text("--allowed-file 'src/example.py'")
    expect(packet_panel.locator('[data-packet-command-preview]')).to_contain_text("--allowed-file 'src/second.py'")
    expect(packet_panel.locator('[data-packet-command-preview]')).not_to_contain_text("<allowed-file>")
    expect(packet_panel.locator('[data-packet-command-preview]')).not_to_contain_text("<verification-command>")

    packet_panel.locator('[data-create-serial-packet]').click()
    expect(page.locator("#next-task-command-output")).to_contain_text("Exit 0", timeout=15_000)
    runtime_panel = page.locator("#serial-runtime-panel")
    expect(runtime_panel).to_contain_text("Worker Runtime", timeout=15_000)
    expect(runtime_panel).to_contain_text("qwen-worker", timeout=15_000)
    expect(runtime_panel).to_contain_text("not_started", timeout=15_000)
    expect(runtime_panel).to_contain_text("not_run", timeout=15_000)
    expect(runtime_panel).to_contain_text("completion-verifier.py", timeout=15_000)
    expect(runtime_panel).to_contain_text("next safe action", timeout=15_000)
    packet_dirs = list((scratch_state.root / ".devflow" / "local-agent-runs").glob("*"))
    assert packet_dirs
    expect(runtime_panel).to_contain_text(packet_dirs[0].name, timeout=15_000)
    manifest = json.loads((packet_dirs[0] / "run.json").read_text(encoding="utf-8"))
    assert manifest["runtime"]["kind"] == "hermes-profile"
    assert manifest["runtime"]["hermes_profile"] == "qwen-worker"
    assert manifest["allowed_files"] == ["src/example.py", "src/second.py"]
    assert manifest["verification_commands"] == [
        {"order": 1, "command": "python -m pytest tests/example.py -q"}
    ]
    assert manifest["safety"]["model_launch"] is False
    assert manifest["safety"]["git_mutation"] is False
    assert not (packet_dirs[0] / "hermes-run.json").exists()


def test_runtime_panel_shows_ready_and_failed_hermes_run_evidence(
    browser_page: tuple[Page, list[str]],
    scratch_state: ScratchState,
) -> None:
    page, _console_errors = browser_page

    ready = create_serial_local_agent_run(
        scratch_state.root,
        run_id="ui-ready-for-verifier",
        phase="implementer",
        provider="ollama",
        model="qwen3.6-32b-256k:latest",
        allowed_files=["src/example.py"],
        verification_commands=["python -m pytest tests/example.py -q"],
        runtime_kind="hermes-profile",
        hermes_profile="qwen-worker",
        toolsets=["file", "terminal"],
    )
    _write_hermes_launch_evidence(ready.run_dir, "ui-ready-for-verifier", launch_status="completed", exit_code=0)
    page.reload(wait_until="domcontentloaded")
    _wait_for_hydration(page)

    runtime_panel = page.locator("#serial-runtime-panel")
    expect(runtime_panel).to_contain_text("ui-ready-for-verifier")
    expect(runtime_panel).to_contain_text("ready_for_verifier")
    expect(runtime_panel).to_contain_text("completed")
    expect(runtime_panel).to_contain_text("Run completion-verifier.py")
    expect(runtime_panel).to_contain_text("hermes-run.json")
    expect(runtime_panel.locator("[data-copy-serial-command]")).to_be_visible()

    time.sleep(0.02)
    failed = create_serial_local_agent_run(
        scratch_state.root,
        run_id="ui-failed-hermes-run",
        phase="implementer",
        provider="ollama",
        model="qwen3.6-32b-256k:latest",
        allowed_files=["src/example.py"],
        verification_commands=["python -m pytest tests/example.py -q"],
        runtime_kind="hermes-profile",
        hermes_profile="qwen-worker",
        toolsets=["file", "terminal"],
    )
    _write_hermes_launch_evidence(failed.run_dir, "ui-failed-hermes-run", launch_status="failed", exit_code=7)
    page.reload(wait_until="domcontentloaded")
    _wait_for_hydration(page)

    expect(runtime_panel).to_contain_text("ui-failed-hermes-run")
    expect(runtime_panel).to_contain_text("failed")
    expect(runtime_panel).to_contain_text("Inspect Hermes launch stdout/stderr")
    expect(runtime_panel).to_contain_text("hermes-stderr.txt")


def test_no_ai_worker_option_keeps_shell_fallback_click_flow(
    browser_page: tuple[Page, list[str]],
    scratch_state: ScratchState,
) -> None:
    page, _console_errors = browser_page

    created = _run_devflow(scratch_state.root, scratch_state.devflow_home, "task", "create", "Browser shell only contract")
    task_id = next(part.rstrip(":") for part in created.stdout.split() if part.startswith("task-"))
    page.reload(wait_until="domcontentloaded")
    _wait_for_hydration(page)

    page.locator("#active-work-groups .worker-card", has_text="Browser shell only contract").locator("[data-select-task]").first.click()
    panel = page.locator("#next-task-shell-panel")
    expect(panel).to_be_visible()
    assert panel.locator('[data-worker-option-card][data-worker-action-kind="serial_packet"]').count() == 0
    _open_shell_fallback(page)
    expect(panel.locator(".nt-shell-fallback [data-task-run-shell]")).to_be_visible()
    panel.locator('[data-shell-command]').fill("printf shell-only > shell-only.txt")
    panel.locator('[data-task-run-shell]').click()
    expect(page.locator("#next-task-command-output")).to_contain_text("Succeeded", timeout=15_000)
    assert (scratch_state.root / ".devflow" / "workspaces" / task_id / "shell-only.txt").exists()


def test_policy_blocked_hermes_run_never_executes_from_browser(
    browser_page: tuple[Page, list[str]],
    scratch_state: ScratchState,
) -> None:
    page, _console_errors = browser_page

    page.evaluate("""async () => { await runApprovedCommand('devflow agent hermes-run ui-policy-packet --profile qwen-worker --json', {}); }""")
    output = page.locator("#next-task-command-output")
    expect(output).to_contain_text("Blocked by policy", timeout=15_000)
    expect(output).to_contain_text("approval_required_worker_runtime", timeout=15_000)
    expect(output).to_contain_text("command runs workers", timeout=15_000)
    assert not (scratch_state.root / ".devflow" / "local-agent-runs" / "ui-policy-packet" / "hermes-run.json").exists()


def test_focus_overlay_shows_ai_worker_packet_controls(browser_page: tuple[Page, list[str]]) -> None:
    page, _console_errors = browser_page

    page.locator("#active-work-groups .worker-card", has_text="Browser active work").locator("[data-inspect-task]").first.click()
    focus = page.locator("#focus-content")
    expect(focus).to_contain_text("Browser active work")
    packet_panel = focus.locator("#focus-task-packet-panel")
    expect(packet_panel).to_be_hidden()

    blocked_card = focus.locator('[data-worker-option-card][data-worker-id="blocked-local-worker"]').first
    expect(blocked_card).to_be_visible()
    expect(blocked_card).to_contain_text("Runtime lock is busy")
    blocked_card.click(force=True)
    expect(packet_panel).to_be_hidden()
    expect(focus.locator("#focus-command-output")).to_contain_text("Runtime lock is busy")

    ai_card = focus.locator('[data-worker-option-card][data-worker-action-kind="serial_packet"]').first
    expect(ai_card).to_be_visible()
    ai_card.click()
    expect(packet_panel).to_be_visible()
    expect(packet_panel).to_contain_text("Create serial packet")
    expect(packet_panel).to_contain_text("Hermes Qwen Implementer")
    expect(packet_panel.locator('[data-packet-allowed-files]')).to_be_visible()
    expect(packet_panel.locator('[data-packet-verify-command]')).to_be_visible()
    expect(packet_panel.locator('[data-packet-command-preview]')).to_contain_text("devflow agent serial-packet")
    expect(page.locator("#next-task-packet-panel")).to_be_hidden()


def test_action_errors_share_launchpad_surface_without_unwanted_posts(
    browser_page: tuple[Page, list[str]],
) -> None:
    page, _console_errors = browser_page

    page.evaluate(
        """() => {
          window.__actionPostCount = 0;
          const originalFetch = window.fetch.bind(window);
          window.fetch = (...args) => {
            const url = String(args[0] || '');
            const init = args[1] || {};
            if (url.includes('/api/actions/run') && String(init.method || 'GET').toUpperCase() === 'POST') {
              window.__actionPostCount += 1;
            }
            return originalFetch(...args);
          };
        }"""
    )

    page.locator("#active-work-groups .worker-card", has_text="Browser active work").locator("[data-select-task]").first.click()
    page.locator('[data-worker-option-card][data-worker-action-kind="serial_packet"]').first.click()
    packet_panel = page.locator("#next-task-packet-panel")
    packet_panel.locator('[data-packet-allowed-files]').fill("")
    packet_panel.locator('[data-packet-verify-command]').fill("python -m pytest tests/example.py -q")
    page.evaluate(
        """async () => {
          const button = document.querySelector('[data-create-serial-packet]');
          button.disabled = false;
          button.click();
          await new Promise(resolve => setTimeout(resolve, 50));
        }"""
    )
    output = page.locator("#next-task-command-output")
    expect(output).to_contain_text("Validation error")
    expect(output).to_contain_text("Enter at least one allowed file path")
    assert page.evaluate("() => window.__actionPostCount") == 0

    _open_shell_fallback(page)
    page.locator("#next-task-shell-panel [data-shell-command]").fill("<command>")
    page.locator("#next-task-shell-panel [data-task-run-shell]").click()
    expect(output).to_contain_text("Validation error")
    expect(output).to_contain_text("concrete command inputs")
    assert page.evaluate("() => window.__actionPostCount") == 0

    page.evaluate("""async () => { await runApprovedCommand('devflow task cleanup task-0001 --apply', {}); }""")
    expect(output).to_contain_text("Blocked by policy", timeout=15_000)
    expect(output).to_contain_text("approval_required_task_state", timeout=15_000)
    expect(output).to_contain_text("command creates, closes, finalizes", timeout=15_000)
    assert page.evaluate("() => window.__actionPostCount") == 1


def test_review_queue_selects_promotion_candidate_and_runs_preview(browser_page: tuple[Page, list[str]]) -> None:
    page, _console_errors = browser_page

    expect(page.locator("#guided-review-queue")).to_contain_text("Browser promotion candidate")
    page.locator("#guided-review-queue [data-select-task='task-0002']").first.click()
    expect(page.locator("#orchestrator-goal-title")).to_contain_text("task-0002")
    expect(page.locator("#orchestrator-goal-title")).to_contain_text("Browser promotion candidate")
    expect(page.locator("#next-task-action-slot")).to_contain_text("Review preview")

    page.locator("#next-task-action-slot [data-command*='promote-preview']").first.click()
    expect(page.locator("#next-task-command-output")).to_contain_text("Exit 0", timeout=15_000)


def test_brainstorm_definition_of_done_persists_per_session(browser_page: tuple[Page, list[str]]) -> None:
    page, _console_errors = browser_page
    done_text = "Launchpad shows the selected task and start controls."

    session_id = page.evaluate("() => localStorage.getItem('devflow-brainstorm-session')")
    assert isinstance(session_id, str)
    page.locator("#brainstorm-definition-of-done").fill(done_text)
    stored = page.evaluate(
        """(sessionId) => localStorage.getItem(`devflow-brainstorm-definition-of-done:${sessionId}`)""",
        session_id,
    )
    assert stored == done_text

    page.locator("#brainstorm-new-session-side").click()
    expect(page.locator("#brainstorm-definition-of-done")).to_have_value("")
    new_session_id = page.evaluate("() => localStorage.getItem('devflow-brainstorm-session')")
    assert new_session_id != session_id


def test_action_api_blocks_unsafe_commands(
    browser_page: tuple[Page, list[str]],
    operating_layer_url: str,
    scratch_state: ScratchState,
) -> None:
    page, _console_errors = browser_page

    blocked = page.evaluate(
        """async ({ url, phrase }) => {
          const command = "devflow task apply-patch task-0001";
          const response = await fetch(`${url}/api/actions/run`, {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({
              command,
              human_approved: true,
              approval_phrase: phrase,
              approved_command: command
            })
          });
          return {status: response.status, payload: await response.json()};
        }""",
        {"url": operating_layer_url, "phrase": APPROVAL_PHRASE},
    )
    assert blocked["status"] == 409
    assert blocked["payload"]["executed"] is False

    unsafe_commands = [
        "devflow task cleanup task-0001 --apply",
        "devflow sync-main",
        "devflow push-main",
        "devflow project connect-github demo --remote-url https://github.com/example/demo",
        "devflow agent hermes-run browser-policy-packet --profile qwen-worker --json",
    ]
    for command in unsafe_commands:
        payload = _post_browser_action(page, operating_layer_url, command)
        assert payload["status"] == 409, command
        assert payload["payload"]["executed"] is False

    packet_command = (
        "devflow agent serial-packet --phase implementer --provider ollama "
        "--model qwen3.6-32b-256k:latest --task-id task-0001 --worker-id qwen-worker "
        "--runtime hermes-profile --hermes-profile qwen-worker --toolset file --toolset terminal "
        "--run-id browser-policy-packet --allowed-file src/example.py "
        "--verify 'python -m pytest tests/example.py -q'"
    )
    packet_payload = _post_browser_action(page, operating_layer_url, packet_command)
    assert packet_payload["status"] == 200, packet_payload
    assert packet_payload["payload"]["executed"] is True
    assert packet_payload["payload"]["exit_code"] == 0
    packet_dir = scratch_state.root / ".devflow" / "local-agent-runs" / "browser-policy-packet"
    assert (packet_dir / "run.json").exists()
    assert (packet_dir / "worker-packet.md").exists()
    manifest = json.loads((packet_dir / "run.json").read_text(encoding="utf-8"))
    assert manifest["runtime"]["kind"] == "hermes-profile"
    assert manifest["runtime"]["hermes_profile"] == "qwen-worker"
    assert manifest["safety"]["model_launch"] is False
    assert manifest["safety"]["git_mutation"] is False
    assert not (packet_dir / "hermes-run.json").exists()

    invalid = page.evaluate(
        """async (url) => {
          const response = await fetch(`${url}/api/actions/run`, {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: "{not-json"
          });
          return {status: response.status, payload: await response.json()};
        }""",
        operating_layer_url,
    )
    assert invalid["status"] == 400
    assert "invalid JSON body" in invalid["payload"]["error"]


def test_task_switcher_and_seeded_evidence_lane(browser_page: tuple[Page, list[str]]) -> None:
    page, _console_errors = browser_page

    expect(page.locator("#active-work-groups")).to_contain_text("Local model evidence lane")
    expect(page.locator("#guided-evidence-stream")).to_contain_text("task-0004")
    page.locator("#active-work-groups .worker-card", has_text="Local model evidence lane").locator("[data-select-task]").first.click()
    expect(page.locator("#orchestrator-goal-title")).to_contain_text("task-0004")
    expect(page.locator("#next-task-meta")).to_contain_text("local-qwopus-inspector")
    expect(page.locator("#next-task-latest-evidence")).to_contain_text("Latest Evidence")
    expect(page.locator("#orchestrator-agent-progress")).to_contain_text("task-0001")
    expect(page.locator("#orchestrator-agent-progress")).to_contain_text("task-0004")


def test_worker_lanes_are_overview_not_primary_action_surface(browser_page: tuple[Page, list[str]]) -> None:
    page, _console_errors = browser_page

    expect(page.locator("#active-work-groups")).to_contain_text("Browser active work")
    assert page.locator("#active-work-groups [data-task-run-shell]").count() == 0
    assert page.locator("#active-work-groups [data-task-verify]").count() == 0
    expect(page.locator("#active-work-groups [data-select-task]").first).to_be_visible()
    assert "active" in str(page.locator('[data-nav="home"]').get_attribute("class") or "")
    assert page.locator("#orchestrator-section").evaluate("element => element.getAttribute('aria-label')") == "Next Task"


def test_visual_regression_cli_writes_current_browser_evidence(scratch_state: ScratchState) -> None:
    result = _run_devflow(
        scratch_state.root,
        scratch_state.devflow_home,
        "operating-layer",
        "visual-qa",
        "--write-current",
        "--json",
    )
    payload = json.loads(result.stdout)

    assert payload["surface"] == "operating-layer"
    assert payload["playwright_assertions"]
    viewports = {artifact["viewport"] for artifact in payload["image_fallback"]["artifacts"]}
    assert {"desktop", "mobile"} <= viewports
    for artifact in payload["image_fallback"]["artifacts"]:
        assert (scratch_state.root / artifact["current_png"]).exists()


@pytest.mark.ui_browser_live
def test_live_local_model_action_runs_only_when_enabled(
    browser_page: tuple[Page, list[str]],
    operating_layer_url: str,
    scratch_state: ScratchState,
) -> None:
    if os.environ.get("DEVFLOW_UI_LIVE_LOCAL_MODELS") != "1":
        pytest.skip("Set DEVFLOW_UI_LIVE_LOCAL_MODELS=1 for live local-model browser signoff.")

    pytest.skip("Launchpad browser signoff does not exercise live local-model execution yet.")


def _run_devflow(cwd: Path, devflow_home: Path, *args: str, timeout: int = 60) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [PYTHON.as_posix(), "-m", "devflow.cli", *args],
        cwd=cwd,
        env=_devflow_env(devflow_home),
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    assert result.returncode == 0, f"devflow {' '.join(args)} failed\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    return result


def _devflow_env(devflow_home: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = f"{REPO_ROOT / 'src'}:{REPO_ROOT}"
    env["DEVFLOW_HOME"] = devflow_home.as_posix()
    env.setdefault("DEVFLOW_EXPERIMENTAL", "1")
    return env


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_healthz(base_url: str, process: subprocess.Popen[str]) -> None:
    deadline = time.time() + 10
    last_error: Exception | None = None
    while time.time() < deadline:
        if process.poll() is not None:
            stdout, stderr = process.communicate(timeout=1)
            raise AssertionError(f"operating-layer server exited early\nSTDOUT:\n{stdout}\nSTDERR:\n{stderr}")
        try:
            with urllib.request.urlopen(f"{base_url}/healthz", timeout=1) as response:
                if response.status == 200:
                    return
        except (OSError, urllib.error.URLError) as exc:
            last_error = exc
            time.sleep(0.1)
    raise AssertionError(f"operating-layer server did not become healthy: {last_error}")


def _wait_for_hydration(page: Page) -> None:
    expect(page.locator("#orchestrator-section")).to_be_visible(timeout=10_000)
    expect(page.locator("#active-work-groups")).to_contain_text("Browser active work", timeout=10_000)
    page.wait_for_function(
        """() => {
          const cards = document.querySelectorAll('#active-work-groups .worker-card').length;
          const command = document.querySelector('#orchestrator-command')?.textContent || '';
          return cards >= 1 && !command.includes('Loading');
        }""",
        timeout=10_000,
    )


def _no_horizontal_overflow(page: Page) -> bool:
    return bool(
        page.evaluate(
            """() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1
              && document.body.scrollWidth <= document.body.clientWidth + 1"""
        )
    )


def _install_clipboard_spy(page: Page) -> None:
    page.evaluate(
        """() => {
          window.__copiedText = '';
          Object.defineProperty(navigator, 'clipboard', {
            configurable: true,
            value: {
              writeText: async (text) => {
                window.__copiedText = text;
              }
            }
          });
        }"""
    )


def _open_shell_fallback(page: Page) -> None:
    details = page.locator("#next-task-shell-panel .nt-shell-fallback details")
    expect(details).to_be_visible()
    if not details.evaluate("element => element.open"):
        details.locator("summary").click()
    expect(details.locator("[data-task-run-shell]")).to_be_visible()


def _home_layout_metrics(page: Page) -> dict[str, int]:
    return page.evaluate(
        """() => {
          const rect = (selector) => {
            const element = document.querySelector(selector);
            if (!element) return { top: 99999, height: 0 };
            const box = element.getBoundingClientRect();
            return { top: Math.round(box.top), height: Math.round(box.height) };
          };
          const idea = rect("#idea-greenhouse-section");
          const brainstorm = rect("#brainstorm-section");
          const pipeline = rect("#pipeline-spine");
          const nextTask = rect("#orchestrator-section");
          const active = rect("#product-review-section");
          const workerLanes = rect("#active-work-groups");
          const reviewQueue = rect("#guided-review-queue");
          const evidenceStream = rect("#guided-evidence-stream");
          return {
            scroll_y: Math.round(window.scrollY),
            viewport_height: Math.round(window.innerHeight),
            idea_top: idea.top,
            brainstorm_top: brainstorm.top,
            pipeline_top: pipeline.top,
            next_task_top: nextTask.top,
            active_top: active.top,
            active_height: active.height,
            worker_lanes_top: workerLanes.top,
            review_queue_top: reviewQueue.top,
            evidence_stream_top: evidenceStream.top,
            closed_guided_cards: document.querySelectorAll("#active-work-groups .guided-task-card.closed").length,
          };
        }"""
    )


def _write_question(root: Path, task_id: str) -> None:
    question_path = root / ".devflow" / "tasks" / task_id / "agents" / "devflow-manual-codex-worker" / "questions.jsonl"
    question_path.parent.mkdir(parents=True, exist_ok=True)
    question_path.write_text(
        json.dumps(
            {
                "type": "blocked_question",
                "task_id": task_id,
                "agent_id": "devflow-manual-codex-worker",
                "question": "Which UI path should the worker preserve?",
                "blocking_reason": "Two operator flows overlap.",
                "required_decision": "Choose the browser-first path.",
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def _write_hermes_launch_evidence(
    run_dir: Path,
    run_id: str,
    *,
    launch_status: str,
    exit_code: int,
) -> None:
    stdout_path = run_dir / "hermes-stdout.txt"
    stderr_path = run_dir / "hermes-stderr.txt"
    stdout_path.write_text("fake hermes stdout\n", encoding="utf-8")
    stderr_path.write_text("fake hermes stderr\n" if exit_code else "", encoding="utf-8")
    run_dir.joinpath("hermes-run.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "will_launch_hermes": True,
                "dry_run": False,
                "run_id": run_id,
                "hermes_profile": "qwen-worker",
                "runtime_kind": "hermes-profile",
                "launch_status": launch_status,
                "exit_code": exit_code,
                "stdout_path": f".devflow/local-agent-runs/{run_id}/hermes-stdout.txt",
                "stderr_path": f".devflow/local-agent-runs/{run_id}/hermes-stderr.txt",
                "hermes_run_path": f".devflow/local-agent-runs/{run_id}/hermes-run.json",
                "verification_ran": False,
                "next_safe_action": "Run completion-verifier.py from the packet directory.",
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def _post_browser_action(page: Page, operating_layer_url: str, command: str) -> dict[str, Any]:
    return page.evaluate(
        """async ({ url, command, phrase }) => {
          const response = await fetch(`${url}/api/actions/run`, {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({
              command,
              human_approved: true,
              approval_phrase: phrase,
              approved_command: command
            })
          });
          return {status: response.status, payload: await response.json()};
        }""",
        {"url": operating_layer_url, "command": command, "phrase": APPROVAL_PHRASE},
    )


def _select_fast_installed_local_profile(scratch_state: ScratchState) -> str | None:
    catalog = json.loads(
        _run_devflow(scratch_state.root, scratch_state.devflow_home, "agent", "catalog", "--json").stdout
    )
    installed = {item["name"] for item in catalog.get("local_ollama", {}).get("installed_models", [])}
    preferred_models = [
        "qwen2.5-coder:1.5b",
        "local-coder-tiny:latest",
        "gemma4-fast:latest",
        "local-worker-fast:latest",
    ]
    profiles = [
        profile
        for profile in catalog.get("profiles", [])
        if profile.get("provider") == "ollama"
        and profile.get("model") in installed
        and (profile.get("runtime_contract") or {}).get("execution_surface") == "agent_run"
    ]
    for model in preferred_models:
        for profile in profiles:
            if profile.get("model") == model:
                return str(profile["id"])
    return str(profiles[0]["id"]) if profiles else None
