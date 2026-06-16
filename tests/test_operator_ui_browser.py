from __future__ import annotations

import json
import os
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

    expect(page.get_by_role("link", name="Home")).to_have_attribute("aria-current", "page")
    expect(page.get_by_role("link", name="Advanced")).to_be_visible()
    expect(page.get_by_role("heading", name="Browser active work")).to_be_visible()
    assert _no_horizontal_overflow(page)
    assert console_errors == []


def test_home_prioritizes_idea_capture_without_closed_history_noise(
    browser_page: tuple[Page, list[str]],
) -> None:
    page, _console_errors = browser_page

    desktop = _home_layout_metrics(page)
    assert desktop["scroll_y"] == 0
    assert desktop["idea_top"] < 220
    assert desktop["next_top"] < desktop["viewport_height"]
    assert desktop["active_height"] <= desktop["viewport_height"] * 1.35
    assert desktop["closed_guided_cards"] == 0

    page.set_viewport_size({"width": 390, "height": 900})
    mobile = _home_layout_metrics(page)
    assert mobile["scroll_y"] == 0
    assert mobile["idea_top"] < 220
    assert mobile["next_top"] < mobile["viewport_height"]
    assert mobile["active_height"] <= mobile["viewport_height"] * 1.35
    assert mobile["closed_guided_cards"] == 0
    assert _no_horizontal_overflow(page)


def test_navigation_hash_history_and_mobile_viewport(browser_page: tuple[Page, list[str]]) -> None:
    page, _console_errors = browser_page

    for label, hash_value in [
        ("Work", "#lanes"),
        ("Review", "#promotion"),
        ("Projects", "#projects"),
        ("Advanced", "#actions"),
        ("Home", "#orchestrator"),
    ]:
        page.get_by_role("link", name=label).click()
        page.wait_for_function("(hashValue) => window.location.hash === hashValue", arg=hash_value)
        expect(page.get_by_role("link", name=label)).to_have_attribute("aria-current", "page")

    page.go_back(wait_until="domcontentloaded")
    page.wait_for_function("() => window.location.hash === '#actions'")
    page.go_forward(wait_until="domcontentloaded")
    page.wait_for_function("() => window.location.hash === '#orchestrator'")

    page.set_viewport_size({"width": 390, "height": 900})
    expect(page.get_by_role("link", name="Work")).to_be_visible()
    assert _no_horizontal_overflow(page)


def test_guided_controls_create_idea_task_and_shell_worker(
    browser_page: tuple[Page, list[str]],
    scratch_state: ScratchState,
) -> None:
    page, _console_errors = browser_page

    page.locator("#idea-intake-title").fill("Browser idea capture")
    page.locator("#idea-intake-text").fill("Capture this browser-driven idea without running workers.")
    page.locator("#idea-intake-submit").click()
    expect(page.locator("#guided-action-result")).to_contain_text("Exit 0", timeout=10_000)
    assert (scratch_state.root / ".devflow" / "ideas" / "I-0001" / "idea.json").exists()

    page.get_by_text("Create an immediate task instead").click()
    page.locator("#start-work-title").fill("Browser created worktree task")
    page.locator("#start-work-git-worktree").check()
    page.locator("#start-work-submit").click()
    expect(page.locator("#guided-action-result")).to_contain_text("Created task-0005", timeout=15_000)
    assert (scratch_state.root / ".devflow" / "tasks" / "task-0005" / "task.yaml").exists()
    assert (scratch_state.root / ".devflow" / "worktrees" / "task-0005").exists()

    page.get_by_role("link", name="Work").click()
    page.locator("#global-filter").fill("Browser active work")
    page.get_by_role("link", name="Advanced").click()
    page.locator(".action-item", has_text="devflow task run task-0001 --worker shell").first.click()
    page.locator("[data-shell-run-command]").fill("printf browser-run > browser-run.txt")
    page.locator("[data-shell-run-timeout]").fill("10")
    page.locator("[data-run-action]").click()
    expect(page.locator("#action-preview")).to_contain_text("Exit 0", timeout=15_000)
    assert (scratch_state.root / ".devflow" / "workspaces" / "task-0001" / "browser-run.txt").exists()
    assert not (scratch_state.root / "browser-run.txt").exists()


def test_work_surfaces_filter_context_evidence_and_keyboard_clear(browser_page: tuple[Page, list[str]]) -> None:
    page, _console_errors = browser_page

    page.get_by_role("link", name="Work").click()
    expect(page.locator("#lane-board")).to_be_visible()
    expect(page.locator("#agent-cards")).to_contain_text("shell")
    expect(page.locator("#model-catalog-list")).to_contain_text("local-qwopus-inspector")

    page.locator("#global-filter").fill("Local model evidence lane")
    expect(page.locator("#filter-count")).not_to_have_text("All")
    expect(page.locator("#lane-board")).to_contain_text("Local model evidence lane")
    page.keyboard.press("Escape")
    expect(page.locator("#filter-count")).to_have_text("All")

    page.locator("#lane-board .task-row", has_text="Local model evidence lane").click()
    expect(page.locator("#selected-details")).to_contain_text("task-0004")
    expect(page.locator("#detail-summary")).to_contain_text("local-qwopus-inspector")
    assert page.locator("#clear-context-button").is_disabled()
    expect(page.locator("#context-title")).to_contain_text("All work")


def test_review_surfaces_questions_promotion_context_and_approval(browser_page: tuple[Page, list[str]], scratch_state: ScratchState) -> None:
    page, _console_errors = browser_page

    page.get_by_role("link", name="Review").click()
    expect(page.locator("#guided-review-queue")).to_contain_text("Browser promotion candidate")
    expect(page.locator("#inbox")).to_contain_text("Question & Blocker Inbox")
    expect(page.locator("#promotion-list")).to_contain_text("task-0002")

    page.locator("#global-filter").fill("Browser promotion candidate")
    page.get_by_role("link", name="Advanced").click()
    page.locator(".action-item", has_text="devflow task promote task-0002").first.click()
    page.locator("#action-preview [data-promotion-context]").fill("Browser approval captured promotion context.")
    page.locator("[data-run-action]").click()
    expect(page.locator("#action-preview")).to_contain_text("Promotion complete", timeout=15_000)

    assert (scratch_state.root / "approval.txt").read_text(encoding="utf-8") == "ready"
    context = scratch_state.root / ".devflow" / "tasks" / "task-0002" / "promotion-context.md"
    assert "Browser approval captured promotion context." in context.read_text(encoding="utf-8")
    assert APPROVAL_PHRASE in page.locator("#action-preview").inner_text() or "Exit 0" in page.locator("#action-preview").inner_text()


def test_projects_toggle_cards_missing_state_and_project_scoped_actions(
    browser_page: tuple[Page, list[str]],
    scratch_state: ScratchState,
) -> None:
    page, _console_errors = browser_page
    snapshot_requests: list[str] = []
    page.on("request", lambda request: snapshot_requests.append(request.url) if "/api/snapshot" in request.url else None)

    page.get_by_role("link", name="Projects").click()
    expect(page.locator("#project-list")).to_contain_text("Demo Project")
    expect(page.locator("#project-list")).to_contain_text("Missing Project")
    assert page.locator(".project-card.missing").first.is_disabled()

    page.locator(".project-card", has_text="Demo Project").click()
    expect(page.locator("#repo-title")).to_contain_text("registered-project")
    page.get_by_role("link", name="Work").click()
    expect(page.locator("#lane-board")).to_contain_text("Project scoped browser task")
    assert any("project=demo" in url for url in snapshot_requests)

    page.get_by_role("link", name="Advanced").click()
    page.locator("#map-list .map-node", has_text="Projects").click()
    page.locator(".action-item", has_text="Project status").first.click()
    page.locator("[data-run-action]").click()
    expect(page.locator("#action-preview")).to_contain_text("Exit 0", timeout=10_000)
    expect(page.locator("#action-preview")).to_contain_text("demo")

    page.locator("#all-projects-button").click()
    expect(page.locator("#repo-title")).to_contain_text(scratch_state.root.name)


def test_advanced_commands_execute_errors_truncate_and_block_unsafe(
    browser_page: tuple[Page, list[str]],
    operating_layer_url: str,
) -> None:
    page, _console_errors = browser_page

    page.get_by_role("link", name="Advanced").click()
    page.locator("#map-list .map-node", has_text="Projects").click()
    page.locator(".action-item", has_text="devflow git status").first.click()
    page.locator("[data-run-action]").click()
    expect(page.locator("#action-preview")).to_contain_text("Exit 0", timeout=10_000)

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
    ]
    for command in unsafe_commands:
        payload = _post_browser_action(page, operating_layer_url, command)
        assert payload["status"] == 409, command
        assert payload["payload"]["executed"] is False

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


def test_local_models_render_catalog_and_seeded_evidence_lane(browser_page: tuple[Page, list[str]]) -> None:
    page, _console_errors = browser_page

    page.get_by_role("link", name="Work").click()
    expect(page.locator("#model-catalog-list")).to_contain_text("ollama")
    expect(page.locator("#model-catalog-list")).to_contain_text("local-qwopus-inspector")
    page.locator(".model-catalog-row", has_text="local-qwopus-inspector").locator("button", has_text="Use model").click()
    expect(page.locator("#action-preview")).to_contain_text("Command Preview")
    expect(page.locator("#action-preview")).not_to_contain_text("<task-id>")

    page.locator("#global-filter").fill("Local model evidence lane")
    expect(page.locator("#lane-board")).to_contain_text("Local model evidence lane")
    expect(page.locator("#detail-summary")).to_contain_text("local-qwopus-inspector")


def test_keyboard_accessibility_skip_accordion_escape_and_aria(browser_page: tuple[Page, list[str]]) -> None:
    page, _console_errors = browser_page

    page.keyboard.press("Tab")
    expect(page.locator(".skip-link")).to_be_focused()
    page.keyboard.press("Enter")
    assert page.evaluate("() => document.activeElement && document.activeElement.id") == "main-panel"

    page.get_by_role("link", name="Advanced").click()
    trigger = page.locator('[data-toggle-section="inbox"]').first
    before = trigger.get_attribute("aria-expanded")
    trigger.focus()
    page.keyboard.press(" ")
    expect(trigger).to_have_attribute("aria-expanded", "false" if before == "true" else "true")

    page.locator("#global-filter").fill("Browser active work")
    page.keyboard.press("Escape")
    expect(page.locator("#filter-count")).to_have_text("All")
    expect(page.get_by_role("link", name="Advanced")).to_have_attribute("aria-current", "page")
    assert page.locator(".action-item[aria-pressed='true']").count() >= 1


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

    profile_id = _select_fast_installed_local_profile(scratch_state)
    if profile_id is None:
        pytest.skip("blocked: DEVFLOW_UI_LIVE_LOCAL_MODELS=1 but no installed Ollama profile matched the local catalog.")

    page, _console_errors = browser_page
    page.get_by_role("link", name="Work").click()
    page.locator("#model-catalog-list", has_text=profile_id).locator("button", has_text="Use model").click()
    expect(page.locator("#action-preview")).to_contain_text(f"--profile {profile_id}")
    page.locator("[data-run-action]").click()
    expect(page.locator("#action-preview")).to_contain_text("Exit 0", timeout=25_000)

    runs_dir = scratch_state.root / ".devflow" / "tasks" / "task-0001" / "local-model-runs"
    assert any(path.name == "run.json" for path in runs_dir.glob("*/run.json"))
    assert not (scratch_state.root / "result.txt").exists()
    unsafe = _post_browser_action(page, operating_layer_url, "devflow push-main")
    assert unsafe["status"] == 409


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
    expect(page.locator("#repo-title")).not_to_have_text("Loading...", timeout=10_000)
    expect(page.locator("#active-work-groups")).to_contain_text("Browser active work", timeout=10_000)


def _no_horizontal_overflow(page: Page) -> bool:
    return bool(
        page.evaluate(
            """() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1
              && document.body.scrollWidth <= document.body.clientWidth + 1"""
        )
    )


def _home_layout_metrics(page: Page) -> dict[str, int]:
    return page.evaluate(
        """() => {
          const rect = (selector) => {
            const element = document.querySelector(selector);
            if (!element) return { top: 99999, height: 0 };
            const box = element.getBoundingClientRect();
            return { top: Math.round(box.top), height: Math.round(box.height) };
          };
          const idea = rect(".idea-intake-panel");
          const next = rect(".next-step-panel");
          const active = rect(".active-work-panel");
          return {
            scroll_y: Math.round(window.scrollY),
            viewport_height: Math.round(window.innerHeight),
            idea_top: idea.top,
            next_top: next.top,
            active_height: active.height,
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
