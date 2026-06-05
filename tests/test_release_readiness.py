from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from typer.testing import CliRunner

from devflow.cli import app
from devflow.control_room.release_readiness import build_release_readiness_report, render_release_readiness_report


runner = CliRunner()


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)


def _init_repo(root: Path) -> None:
    _git(root, "init", "-b", "main")
    _git(root, "config", "user.email", "release@example.com")
    _git(root, "config", "user.name", "Release Test")
    (root / ".gitignore").write_text(".devflow/\n", encoding="utf-8")
    (root / "README.md").write_text("# Release Repo\n", encoding="utf-8")
    (root / "docs").mkdir()
    (root / "docs" / "handoff-template.md").write_text("## Next Safe Action\n", encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "commit", "-m", "baseline")


def _seed_release_evidence(root: Path) -> tuple[Path, Path]:
    pytest_log = root / ".devflow" / "release" / "pytest.log"
    stale_log = root / ".devflow" / "release" / "stale-context.log"
    pytest_log.parent.mkdir(parents=True, exist_ok=True)
    pytest_log.write_text("891 passed, 6 skipped in 12.34s\n", encoding="utf-8")
    stale_log.write_text("", encoding="utf-8")

    dogfood_run = root / ".devflow" / "dogfood" / "runs" / "dogfood-release"
    (dogfood_run / "cases" / "operating-layer-visual-qa-hardening" / "artifacts").mkdir(
        parents=True,
        exist_ok=True,
    )
    scorecard = {
        "suite": "production-readiness",
        "threshold_result": {"silver_met": True},
        "total_score": 110,
        "max_score": 110,
    }
    (dogfood_run / "scorecard.yaml").write_text(json.dumps(scorecard), encoding="utf-8")
    (dogfood_run / "run.yaml").write_text(
        json.dumps(
            {
                "suite": "production-readiness",
                "cases_run": [{"case_id": "operating-layer-visual-qa-hardening", "status": "passed"}],
            }
        ),
        encoding="utf-8",
    )
    (dogfood_run / "report.md").write_text("silver_met: yes\n", encoding="utf-8")
    visual_result = dogfood_run / "cases" / "operating-layer-visual-qa-hardening" / "artifacts" / "visual-qa-result.json"
    visual_result.write_text(
        json.dumps(
            {
                "status": "pass",
                "artifacts": [
                    {
                        "viewport": "desktop",
                        "current_png": ".devflow/operating-layer/visual-qa/current/desktop.png",
                        "baseline_png": ".devflow/operating-layer/visual-qa/baseline/desktop.png",
                    },
                    {
                        "viewport": "mobile",
                        "current_png": ".devflow/operating-layer/visual-qa/current/mobile.png",
                        "baseline_png": ".devflow/operating-layer/visual-qa/baseline/mobile.png",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    return pytest_log, stale_log


def test_release_readiness_passes_with_required_evidence(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    pytest_log, stale_log = _seed_release_evidence(tmp_path)

    report = build_release_readiness_report(
        tmp_path,
        pytest_evidence=pytest_log,
        stale_context_evidence=stale_log,
    )

    assert report["status"] == "passed"
    assert {check["id"]: check["status"] for check in report["checks"]} == {
        "clean-devflow-git-status": "passed",
        "full-pytest": "passed",
        "dogfood-production-readiness": "passed",
        "operating-layer-visual-qa-evidence": "passed",
        "stale-context-scan": "passed",
        "standard-handoff-report": "passed",
    }
    rendered = render_release_readiness_report(report)
    assert "## Next Safe Action" in rendered
    assert "tag or build the release" in rendered


def test_release_readiness_blocks_without_pytest_and_stale_context_evidence(tmp_path: Path) -> None:
    _init_repo(tmp_path)

    report = build_release_readiness_report(tmp_path)

    assert report["status"] == "blocked"
    checks = {check["id"]: check for check in report["checks"]}
    assert checks["full-pytest"]["status"] == "needs_evidence"
    assert checks["stale-context-scan"]["status"] == "needs_evidence"
    assert "full pytest" in report["next_safe_action"]


def test_release_readiness_cli_outputs_json(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    pytest_log, stale_log = _seed_release_evidence(tmp_path)
    old_cwd = Path.cwd()
    try:
        os.chdir(tmp_path)
        result = runner.invoke(
            app,
            [
                "release",
                "readiness",
                "--pytest-evidence",
                str(pytest_log),
                "--stale-context-evidence",
                str(stale_log),
                "--json",
            ],
        )
    finally:
        os.chdir(old_cwd)

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "passed"
    assert payload["next_safe_action"].startswith("Release readiness is satisfied")
