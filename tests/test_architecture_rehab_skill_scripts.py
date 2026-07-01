from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1] / "skills" / "improve-codebase-architecture"


def _load_script(name: str):
    path = SKILL_DIR / "scripts" / name
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_graphify_artifacts(repo: Path, *, commit: str = "abc1234") -> None:
    graphify_out = repo / "graphify-out"
    graphify_out.mkdir()
    (graphify_out / "GRAPH_REPORT.md").write_text(
        f"""\
# Graph Report - Sample  (2026-06-28)

## Corpus Check
- 12 files · ~1,234 words

## Summary
- 42 nodes · 84 edges · 6 communities (5 shown, 1 thin omitted)
- Extraction: 90% EXTRACTED · 9% INFERRED · 1% AMBIGUOUS · INFERRED: 8 edges (avg confidence: 0.80)

## Graph Freshness
- Built from commit: `{commit}`
""",
        encoding="utf-8",
    )
    (graphify_out / "graph.json").write_text(
        json.dumps(
            {
                "built_at_commit": commit,
                "nodes": [
                    {"id": "a", "source_file": "src/a.py", "community": 1},
                    {"id": "b", "source_file": "src/b.py", "community": 1},
                    {"id": "c", "source_file": "src/b.py", "community": 2},
                ],
                "links": [
                    {"source": "a", "target": "b"},
                    {"source": "b", "target": "c"},
                    {"source": "b", "target": "a"},
                ],
            }
        ),
        encoding="utf-8",
    )


def test_graphify_rehab_scorecard_reports_freshness_and_delta(tmp_path: Path) -> None:
    score = _load_script("graphify_rehab_score.py")
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_graphify_artifacts(repo)
    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text(
        json.dumps({"metrics": {"nodes": 50, "edges": 90, "communities": 7, "max_file_degree": 5}}),
        encoding="utf-8",
    )

    card = score.compute_scorecard(repo, current_commit="abc1234", baseline_path=baseline_path)

    assert card["commit"]["fresh"] is True
    assert card["metrics"]["files"] == 12
    assert card["metrics"]["nodes"] == 42
    assert card["metrics"]["graph_json_nodes"] == 3
    assert card["metrics"]["max_file_degree"] == 4
    assert card["deltas"] == {
        "nodes": -8,
        "edges": -6,
        "communities": -1,
        "max_file_degree": -1,
    }
    assert card["thresholds"]["fresh_graph"]["status"] == "pass"
    assert card["verdict"] == "pass"


def test_start_rehab_loop_dry_run_writes_goal_and_exact_loop_command(tmp_path: Path) -> None:
    start = _load_script("start_rehab_loop.py")
    repo = tmp_path / "repo"
    repo.mkdir()
    loop_script = tmp_path / "Loop Goal Script" / "loop.py"
    loop_script.parent.mkdir()
    loop_script.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    goal_dir = tmp_path / "goals"

    result = start.prepare_rehab_loop(
        repo,
        candidate="Collapse shallow task projection",
        loop_script=loop_script,
        goal_dir=goal_dir,
        max_iterations=1,
        dry_run=True,
        timestamp="20260628T111500Z",
    )

    goal_file = Path(result["goal_file"])
    assert goal_file.exists()
    goal_text = goal_file.read_text(encoding="utf-8")
    assert "Collapse shallow task projection" in goal_text
    assert "one safe architecture slice" in goal_text
    assert "Planner profile: dfcodex55" in goal_text
    assert "Judge profile: dfcodex55" in goal_text
    assert "## Planner Gate" in goal_text
    assert "Codebase-wide refactor direction." in goal_text
    assert "Current small, testable fix." in goal_text
    assert "The worker must not edit source until the planner plan exists" in goal_text
    assert "Do not commit generated graphify-out/ files" in goal_text
    assert result["command"] == [
        loop_script.as_posix(),
        "start",
        "--goal-file",
        goal_file.as_posix(),
        "--workdir",
        repo.as_posix(),
        "--max-iterations",
        "1",
        "--profile",
        "dflocalfast",
        "--judge-profile",
        "dfcodex55",
        "--planner-profile",
        "dfcodex55",
    ]
    assert result["profile"] == "dflocalfast"
    assert result["planner_profile"] == "dfcodex55"
    assert result["judge_profile"] == "dfcodex55"
    assert result["started"] is False


def test_start_rehab_loop_auto_smoke_uses_minimal_goal_and_no_judge(tmp_path: Path) -> None:
    start = _load_script("start_rehab_loop.py")
    repo = tmp_path / "smoke-repo"
    repo.mkdir()
    loop_script = tmp_path / "Loop Goal Script" / "loop.py"
    loop_script.parent.mkdir()
    loop_script.write_text("#!/usr/bin/env python3\n", encoding="utf-8")

    result = start.prepare_rehab_loop(
        repo,
        candidate="Smoke test loop reliability: inspect the tiny repo, run python -m pytest -q if available, write a clean handoff, and do not change files",
        loop_script=loop_script,
        goal_dir=tmp_path / "goals",
        max_iterations=1,
        dry_run=True,
        timestamp="20260628T111501Z",
    )

    goal_text = Path(result["goal_file"]).read_text(encoding="utf-8")
    assert "Loop-Goal-Script Smoke Test" in goal_text
    assert "python -m pytest -q" in goal_text
    assert "Do not edit source files" in goal_text
    assert "Graphify Ponytail Architecture Rehab Goal" not in goal_text
    assert "Run graphify_rehab_score.py" not in goal_text
    assert "--no-judge" in result["command"]
    assert "--judge-profile" not in result["command"]
    assert "--planner-profile" not in result["command"]
    assert result["goal_template"] == "smoke"
    assert result["planner_profile"] is None
    assert result["judge_profile"] is None
    assert "--session-timeout" in result["command"]
    assert result["command"][result["command"].index("--session-timeout") + 1] == "120"
    assert "--hermes-max-turns" in result["command"]
    assert result["command"][result["command"].index("--hermes-max-turns") + 1] == "2"
    assert "--hermes-toolsets" in result["command"]
    assert result["command"][result["command"].index("--hermes-toolsets") + 1] == "terminal"
    assert "--hermes-ignore-rules" in result["command"]
    assert result["loop_slug"]
    assert result["loop_log"].endswith(f"loop-{result['loop_slug']}.log")


def test_start_rehab_loop_goal_files_do_not_collide_with_same_second_stamp(tmp_path: Path) -> None:
    start = _load_script("start_rehab_loop.py")
    repo = tmp_path / "repo"
    repo.mkdir()
    loop_script = tmp_path / "Loop Goal Script" / "loop.py"
    loop_script.parent.mkdir()
    loop_script.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    goal_dir = tmp_path / "goals"

    first = start.prepare_rehab_loop(
        repo,
        candidate="First same-second candidate",
        loop_script=loop_script,
        goal_dir=goal_dir,
        dry_run=True,
        timestamp="20260628T111502Z",
    )
    second = start.prepare_rehab_loop(
        repo,
        candidate="Second same-second candidate",
        loop_script=loop_script,
        goal_dir=goal_dir,
        dry_run=True,
        timestamp="20260628T111502Z",
    )

    assert first["goal_file"] != second["goal_file"]
    assert Path(first["goal_file"]).exists()
    assert Path(second["goal_file"]).exists()


def test_start_rehab_loop_blocks_real_start_when_profile_preflight_fails(tmp_path: Path) -> None:
    start = _load_script("start_rehab_loop.py")
    repo = tmp_path / "repo"
    repo.mkdir()
    loop_script = tmp_path / "Loop Goal Script" / "loop.py"
    loop_script.parent.mkdir()
    loop_script.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    calls: list[list[str]] = []

    result = start.prepare_rehab_loop(
        repo,
        candidate="No unsafe launch",
        loop_script=loop_script,
        goal_dir=tmp_path / "goals",
        dry_run=False,
        preflight_checker=lambda profile: {"ok": False, "profile": profile, "reason": "missing profile"},
        runner=lambda command: calls.append(command),
    )

    assert result["started"] is False
    assert result["returncode"] == 2
    assert "missing profile" in result["preflight"]["reason"]
    assert calls == []


def test_start_rehab_loop_blocks_real_start_when_codex_judge_preflight_fails(tmp_path: Path) -> None:
    start = _load_script("start_rehab_loop.py")
    repo = tmp_path / "repo"
    repo.mkdir()
    loop_script = tmp_path / "Loop Goal Script" / "loop.py"
    loop_script.parent.mkdir()
    loop_script.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    calls: list[list[str]] = []
    checked_profiles: list[str] = []

    def fake_preflight(profile: str) -> dict[str, object]:
        checked_profiles.append(profile)
        if profile == "dfcodex55":
            return {"ok": False, "profile": profile, "reason": "missing judge profile"}
        return {"ok": True, "profile": profile}

    result = start.prepare_rehab_loop(
        repo,
        candidate="Local worker still needs Codex judge",
        loop_script=loop_script,
        goal_dir=tmp_path / "goals",
        dry_run=False,
        preflight_checker=fake_preflight,
        runner=lambda command: calls.append(command),
    )

    assert result["started"] is False
    assert result["returncode"] == 2
    assert result["planner_preflight"]["reason"] == "missing judge profile"
    assert result["judge_preflight"]["reason"] == "missing judge profile"
    assert checked_profiles == ["dflocalfast", "dfcodex55"]
    assert calls == []


def test_start_rehab_loop_codex_worker_uses_codex55_profile(tmp_path: Path) -> None:
    start = _load_script("start_rehab_loop.py")
    repo = tmp_path / "repo"
    repo.mkdir()
    loop_script = tmp_path / "Loop Goal Script" / "loop.py"
    loop_script.parent.mkdir()
    loop_script.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    calls: list[list[str]] = []

    result = start.prepare_rehab_loop(
        repo,
        candidate="Use Codex worker",
        loop_script=loop_script,
        goal_dir=tmp_path / "goals",
        worker="codex55",
        dry_run=False,
        preflight_checker=lambda profile: {
            "ok": True,
            "profile": profile,
            "model": "gpt-5.5",
            "reason": "remote profile; local model preflight skipped",
        },
        runner=lambda command: calls.append(command),
    )

    goal_text = Path(result["goal_file"]).read_text(encoding="utf-8")
    assert "Worker profile: dfcodex55" in goal_text
    assert "Worker preset: codex55" in goal_text
    assert result["profile"] == "dfcodex55"
    assert result["planner_profile"] == "dfcodex55"
    assert result["judge_profile"] == "dfcodex55"
    assert result["worker"] == "codex55"
    assert result["preflight"]["model"] == "gpt-5.5"
    assert calls == [
        [
            loop_script.as_posix(),
            "start",
            "--goal-file",
            result["goal_file"],
            "--workdir",
            repo.as_posix(),
            "--max-iterations",
            "1",
            "--profile",
            "dfcodex55",
            "--judge-profile",
            "dfcodex55",
            "--planner-profile",
            "dfcodex55",
            "--planner-toolsets",
            "terminal",
            "--hermes-toolsets",
            "terminal",
        ]
    ]


def test_start_rehab_loop_codex_worker_defaults_to_terminal_toolsets(tmp_path: Path) -> None:
    start = _load_script("start_rehab_loop.py")
    repo = tmp_path / "repo"
    repo.mkdir()
    loop_script = tmp_path / "Loop Goal Script" / "loop.py"
    loop_script.parent.mkdir()
    loop_script.write_text("#!/usr/bin/env python3\n", encoding="utf-8")

    result = start.prepare_rehab_loop(
        repo,
        candidate="Use Codex worker with safe toolsets",
        loop_script=loop_script,
        goal_dir=tmp_path / "goals",
        worker="codex55",
        dry_run=True,
        timestamp="20260628T195500Z",
    )

    assert "--planner-toolsets" in result["command"]
    assert result["command"][result["command"].index("--planner-toolsets") + 1] == "terminal"
    assert "--hermes-toolsets" in result["command"]
    assert result["command"][result["command"].index("--hermes-toolsets") + 1] == "terminal"
    assert result["planner_toolsets"] == "terminal"
    assert result["hermes_toolsets"] == "terminal"


def test_start_rehab_loop_passes_planner_toolsets(tmp_path: Path) -> None:
    start = _load_script("start_rehab_loop.py")
    repo = tmp_path / "repo"
    repo.mkdir()
    loop_script = tmp_path / "Loop Goal Script" / "loop.py"
    loop_script.parent.mkdir()
    loop_script.write_text("#!/usr/bin/env python3\n", encoding="utf-8")

    result = start.prepare_rehab_loop(
        repo,
        candidate="Use explicit planner toolsets",
        loop_script=loop_script,
        goal_dir=tmp_path / "goals",
        worker="codex55",
        planner_toolsets="hermes-cli",
        hermes_toolsets="read-only",
        dry_run=True,
        timestamp="20260628T200000Z",
    )

    assert "--planner-toolsets" in result["command"]
    assert result["command"][result["command"].index("--planner-toolsets") + 1] == "hermes-cli"
    assert "--hermes-toolsets" in result["command"]
    assert result["command"][result["command"].index("--hermes-toolsets") + 1] == "read-only"
    assert result["planner_toolsets"] == "hermes-cli"
    assert result["hermes_toolsets"] == "read-only"


def test_preflight_profile_accepts_remote_codex_profile_without_local_probe(tmp_path: Path) -> None:
    start = _load_script("start_rehab_loop.py")
    profile_dir = tmp_path / "profiles" / "dfcodex55"
    profile_dir.mkdir(parents=True)
    (profile_dir / "config.yaml").write_text(
        """\
model:
  default: gpt-5.5
  provider: openai-codex
  base_url: https://chatgpt.com/backend-api/codex
""",
        encoding="utf-8",
    )

    result = start.preflight_profile(
        "dfcodex55",
        hermes_home=tmp_path,
        get_json=lambda url: (_ for _ in ()).throw(AssertionError(url)),
    )

    assert result["ok"] is True
    assert result["profile"] == "dfcodex55"
    assert result["model"] == "gpt-5.5"
    assert result["reason"] == "remote profile; local model preflight skipped"


def test_preflight_profile_accepts_running_local_endpoint(tmp_path: Path) -> None:
    start = _load_script("start_rehab_loop.py")
    profile_dir = tmp_path / "profiles" / "dflocalfast"
    profile_dir.mkdir(parents=True)
    (profile_dir / "config.yaml").write_text(
        """\
model:
  default: qwen36-27b-q5-mtp
  provider: qwen36-27b-q5-mtp
  base_url: http://127.0.0.1:8080/v1
""",
        encoding="utf-8",
    )

    def fake_get_json(url: str) -> dict:
        if url.endswith("/health"):
            return {"status": "ok"}
        if url.endswith("/v1/models"):
            return {"data": [{"id": "qwen36-27b-q5-mtp"}]}
        raise AssertionError(url)

    result = start.preflight_profile("dflocalfast", hermes_home=tmp_path, get_json=fake_get_json)

    assert result["ok"] is True
    assert result["profile"] == "dflocalfast"
    assert result["model"] == "qwen36-27b-q5-mtp"
    assert result["base_url"] == "http://127.0.0.1:8080/v1"


def test_rehab_loop_status_collects_loop_and_latest_scorecard(tmp_path: Path) -> None:
    status = _load_script("rehab_loop_status.py")
    repo = tmp_path / "repo"
    scorecard_dir = repo / ".devflow" / "architecture-rehab" / "scorecards"
    scorecard_dir.mkdir(parents=True)
    (scorecard_dir / "scorecard-old.json").write_text('{"verdict":"fail"}', encoding="utf-8")
    latest = scorecard_dir / "scorecard-new.json"
    latest.write_text('{"verdict":"pass","metrics":{"nodes":42}}', encoding="utf-8")
    loop_script = tmp_path / "Loop Goal Script" / "loop.py"
    loop_script.parent.mkdir()
    loop_script.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    calls: list[list[str]] = []

    def fake_runner(command: list[str]) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        if command[1] == "status":
            return subprocess.CompletedProcess(command, 0, "status output", "")
        return subprocess.CompletedProcess(command, 0, "watch output", "")

    snapshot = status.collect_status(repo, loop_script=loop_script, slug="sample-loop", runner=fake_runner)

    assert calls == [
        [loop_script.as_posix(), "status"],
        [loop_script.as_posix(), "watch", "sample-loop", "--once"],
    ]
    assert snapshot["loop_status"]["stdout"] == "status output"
    assert snapshot["watch"]["stdout"] == "watch output"
    assert snapshot["latest_scorecard"]["path"] == latest.as_posix()
    assert snapshot["latest_scorecard"]["data"]["verdict"] == "pass"
