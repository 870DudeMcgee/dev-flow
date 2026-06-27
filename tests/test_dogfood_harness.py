from __future__ import annotations

import os
import subprocess
from pathlib import Path

import yaml
from typer.testing import CliRunner

from devflow.cli import app
from devflow.control_room import dogfood
from devflow.control_room.dogfood import (
    CATEGORY_MAX,
    production_readiness_cases,
    run_dogfood_suite,
    validate_dogfood_case,
)
from devflow.control_room.dogfood_case_result import (
    CaseResultRecorder,
    write_case_json_artifact,
    write_case_text_artifact,
)
from devflow.control_room.persistence import list_tasks


runner = CliRunner()


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)


def _init_dogfood_repo(root: Path) -> None:
    _git(root, "init", "-b", "main")
    _git(root, "config", "user.email", "dogfood@example.com")
    _git(root, "config", "user.name", "Dogfood Test")
    (root / ".gitignore").write_text(".devflow/\n__pycache__/\n", encoding="utf-8")
    (root / "README.md").write_text("# Dogfood Repo\n", encoding="utf-8")
    skill = root / "skills" / "using-devmode" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("name: using-devmode\n", encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "commit", "-m", "baseline")


def test_case_json_artifact_writer_records_relative_path(tmp_path: Path) -> None:
    state = {"artifacts_created": []}
    artifact_path = tmp_path / "case" / "artifacts" / "summary.json"
    artifact_path.parent.mkdir(parents=True)

    written = write_case_json_artifact(
        state,
        tmp_path,
        artifact_path,
        {"z": 1, "a": {"b": 2}},
    )

    assert written == artifact_path
    assert artifact_path.read_text(encoding="utf-8") == '{\n  "a": {\n    "b": 2\n  },\n  "z": 1\n}\n'
    assert state["artifacts_created"] == ["case/artifacts/summary.json"]


def test_case_text_artifact_writer_records_relative_path(tmp_path: Path) -> None:
    state = {"artifacts_created": []}
    artifact_path = tmp_path / "case" / "artifacts" / "handoff.md"
    artifact_path.parent.mkdir(parents=True)

    written = write_case_text_artifact(state, tmp_path, artifact_path, "# Handoff\n")

    assert written == artifact_path
    assert artifact_path.read_text(encoding="utf-8") == "# Handoff\n"
    assert state["artifacts_created"] == ["case/artifacts/handoff.md"]


def test_case_result_recorder_owns_scores_and_failures(tmp_path: Path) -> None:
    _init_dogfood_repo(tmp_path)
    case = next(item for item in production_readiness_cases() if item["id"] == "tiny-deterministic-docs-task")
    case_dir = tmp_path / ".devflow" / "dogfood" / "runs" / "dogfood-test" / "cases" / case["id"]

    result = CaseResultRecorder(tmp_path, "dogfood-test", case, case_dir)
    result.award("B_pipeline_correctness", 4, True, "task reached verified state")
    result.award("C_context_efficiency", 3, False, "task packet stayed bounded")
    finalized = result.finalize()

    assert finalized["status"] == "failed"
    assert finalized["score"] == 4
    assert finalized["category_scores"]["B_pipeline_correctness"] == 4
    assert finalized["failure_reason"] == "task packet stayed bounded"
    assert finalized["warnings"] == ["missed: task packet stayed bounded"]
    assert finalized["lessons"] == ["task reached verified state"]


def test_case_result_recorder_owns_recording_helpers(tmp_path: Path) -> None:
    _init_dogfood_repo(tmp_path)
    case = next(item for item in production_readiness_cases() if item["id"] == "tiny-deterministic-docs-task")
    case_dir = tmp_path / ".devflow" / "dogfood" / "runs" / "dogfood-test" / "cases" / case["id"]

    result = CaseResultRecorder(tmp_path, "dogfood-test", case, case_dir)
    text_path = result.write_text_artifact(case_dir / "artifacts" / "note.txt", "hello\n")
    json_path = result.write_json_artifact(case_dir / "artifacts" / "summary.json", {"ok": True})
    summary_path = result.write_summary_artifact("case-summary.json", {"score": 1})
    result.record_artifact(tmp_path / "README.md")
    result.record_command("devflow dogfood fixture", status="passed", output="README.md")
    result.record_warning("fixture warning")
    result.record_lesson("fixture lesson")
    result.set_cleanup_status("marker_removed")

    finalized = result.finalize()

    assert text_path == case_dir / "artifacts" / "note.txt"
    assert json_path == case_dir / "artifacts" / "summary.json"
    assert summary_path == case_dir / "artifacts" / "case-summary.json"
    assert finalized["artifacts_created"] == [
        ".devflow/dogfood/runs/dogfood-test/cases/tiny-deterministic-docs-task/artifacts/note.txt",
        ".devflow/dogfood/runs/dogfood-test/cases/tiny-deterministic-docs-task/artifacts/summary.json",
        ".devflow/dogfood/runs/dogfood-test/cases/tiny-deterministic-docs-task/artifacts/case-summary.json",
        "README.md",
    ]
    assert finalized["commands_run"] == [
        {
            "command": "devflow dogfood fixture",
            "status": "passed",
            "exit_code": None,
            "output": "README.md",
        }
    ]
    assert finalized["warnings"] == ["fixture warning"]
    assert finalized["lessons"] == ["fixture lesson"]
    assert finalized["cleanup_status"] == "marker_removed"


def test_case_schema_and_suite_totals() -> None:
    cases = production_readiness_cases()

    assert len(cases) == 19
    assert {case["id"] for case in cases} >= {
        "tiny-deterministic-docs-task",
        "unsafe-worker-outcome",
        "git-native-worker-lane-hardening",
        "local-worker-lane-hardening",
        "registry-runtime-contract",
        "model-audition-evidence",
        "intent-scaffold-approval-path",
        "operator-readiness-reconciliation",
        "simple-scheduler-parallel-coordination",
        "question-blocker-resume-loop",
        "knowledge-capture-from-validation-failure",
        "central-schema-refactor-risk",
        "operating-layer-visual-qa-hardening",
    }
    for case in cases:
        assert validate_dogfood_case(case) == []

    totals = {category: 0 for category in CATEGORY_MAX}
    for case in cases:
        for category, points in case["scoring"].items():
            totals[category] += points
    assert totals == CATEGORY_MAX


def test_run_creates_artifacts_scorecard_and_report(tmp_path: Path) -> None:
    _init_dogfood_repo(tmp_path)

    result = run_dogfood_suite(tmp_path, suite="production-readiness")

    run_dir = tmp_path / result["run_dir"]
    assert (run_dir / "run.yaml").exists()
    assert (run_dir / "scorecard.yaml").exists()
    assert (run_dir / "report.md").exists()
    assert result["scorecard"]["total_score"] >= 82
    assert result["scorecard"]["threshold_result"]["silver_met"] is True
    assert result["scorecard"]["threshold_result"]["no_category_below_70"] is True
    assert len(result["run"]["cases_run"]) == 19
    assert list_tasks(tmp_path) == []

    report = (run_dir / "report.md").read_text(encoding="utf-8")
    assert "threshold:" in report
    assert "provider_api_calls: none" in report
    assert "auto_promotion: none" in report


def test_dogfood_prunes_old_runs_by_default(tmp_path: Path) -> None:
    _init_dogfood_repo(tmp_path)
    runs_dir = tmp_path / ".devflow" / "dogfood" / "runs"
    for name in ["dogfood-19990101T000000Z", "dogfood-19990102T000000Z"]:
        run_dir = runs_dir / name
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "run.yaml").write_text("old: true\n", encoding="utf-8")

    result = run_dogfood_suite(tmp_path, case_ids=["missing-case"])

    retained = sorted(path.name for path in runs_dir.iterdir() if path.is_dir())
    assert retained == [result["run_id"]]
    assert result["pruned_runs"] == [
        ".devflow/dogfood/runs/dogfood-19990101T000000Z",
        ".devflow/dogfood/runs/dogfood-19990102T000000Z",
    ]


def test_dogfood_keep_runs_retains_requested_history(tmp_path: Path) -> None:
    _init_dogfood_repo(tmp_path)
    runs_dir = tmp_path / ".devflow" / "dogfood" / "runs"
    for name in ["dogfood-19990101T000000Z", "dogfood-19990102T000000Z"]:
        run_dir = runs_dir / name
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "run.yaml").write_text("old: true\n", encoding="utf-8")

    result = run_dogfood_suite(tmp_path, case_ids=["missing-case"], keep_runs=2)

    retained = sorted(path.name for path in runs_dir.iterdir() if path.is_dir())
    assert retained == ["dogfood-19990102T000000Z", result["run_id"]]
    assert result["pruned_runs"] == [".devflow/dogfood/runs/dogfood-19990101T000000Z"]


def test_dogfood_can_opt_into_root_runtime_evidence(tmp_path: Path) -> None:
    _init_dogfood_repo(tmp_path)

    result = run_dogfood_suite(
        tmp_path,
        suite="production-readiness",
        case_ids=["tiny-deterministic-docs-task"],
        write_root_runtime_evidence=True,
    )

    assert result["scorecard"]["threshold_result"]["silver_met"] is True
    spawned_tasks = list_tasks(tmp_path)
    assert spawned_tasks
    assert all(task.status == "closed" for task in spawned_tasks)
    assert {task.close_outcome for task in spawned_tasks} == {"evidence-only"}


def test_unsafe_worker_outcome_case_fails_validation_as_expected(tmp_path: Path) -> None:
    _init_dogfood_repo(tmp_path)

    result = run_dogfood_suite(
        tmp_path,
        case_ids=["unsafe-worker-outcome"],
        write_root_runtime_evidence=True,
    )
    case_result = result["results"][0]

    assert case_result["status"] == "passed"
    assert case_result["score"] == case_result["max_score"]
    command = case_result["commands_run"][0]
    assert command["status"] == "failed"
    validation = yaml.safe_load((tmp_path / command["output"]).read_text(encoding="utf-8"))
    assert validation["status"] == "failed"
    assert any("parent traversal is rejected" in error for error in validation["errors"])
    assert any(".git paths are rejected" in error for error in validation["errors"])


def test_success_empty_case_scores_empty_below_useful_result(tmp_path: Path) -> None:
    _init_dogfood_repo(tmp_path)

    result = run_dogfood_suite(tmp_path, case_ids=["success-empty-worker-outcome"])
    case_result = result["results"][0]

    assert case_result["status"] == "passed"
    assert any("success_empty usefulness score 1" in lesson for lesson in case_result["lessons"])
    assert any("empty result is scored below useful result" in lesson for lesson in case_result["lessons"])


def test_plan_only_unsafe_git_case_records_blocked_human_review(tmp_path: Path) -> None:
    _init_dogfood_repo(tmp_path)

    result = run_dogfood_suite(tmp_path, case_ids=["plan-only-unsafe-git-state"])
    case_result = result["results"][0]

    assert case_result["status"] == "passed"
    assert case_result["cleanup_status"] == "marker_removed"
    assert any("dirty Git tree stop condition was active" in lesson for lesson in case_result["lessons"])
    assert not list(tmp_path.glob(".dogfood-dirty-marker-*"))


def test_knowledge_capture_case_creates_proposed_source_linked_knowledge(tmp_path: Path) -> None:
    _init_dogfood_repo(tmp_path)

    result = run_dogfood_suite(
        tmp_path,
        case_ids=["knowledge-capture-from-validation-failure"],
        write_root_runtime_evidence=True,
    )
    case_result = result["results"][0]

    assert case_result["status"] == "passed"
    knowledge_paths = list((tmp_path / ".devflow" / "knowledge").glob("K-*/knowledge.json"))
    assert knowledge_paths
    item = yaml.safe_load(knowledge_paths[0].read_text(encoding="utf-8"))
    assert item["status"] == "proposed"
    assert item["linked_artifacts"]
    assert item["promoted_at"] is None
    assert item["rejected_at"] is None


def test_operating_layer_visual_qa_case_writes_baseline_artifacts(tmp_path: Path, monkeypatch) -> None:
    _init_dogfood_repo(tmp_path)
    import devflow.control_room.operating_layer_visual_qa as visual_qa

    monkeypatch.setattr(visual_qa, "_browser_target_ready", lambda base_url: False)

    result = run_dogfood_suite(
        tmp_path,
        case_ids=["operating-layer-visual-qa-hardening"],
        write_root_runtime_evidence=True,
    )
    case_result = result["results"][0]

    assert case_result["status"] == "passed"
    assert case_result["score"] == case_result["max_score"]
    assert any("desktop and mobile visual QA paths were exercised" in lesson for lesson in case_result["lessons"])
    visual_result_path = next(path for path in case_result["artifacts_created"] if path.endswith("visual-qa-result.json"))
    visual_result = yaml.safe_load((tmp_path / visual_result_path).read_text(encoding="utf-8"))
    assert visual_result["status"] == "pass"
    assert visual_result["capture_method"] == "deterministic-snapshot-fallback"
    assert {artifact["viewport"] for artifact in visual_result["artifacts"]} == {"desktop", "mobile"}
    for artifact in visual_result["artifacts"]:
        assert artifact["status"] == "pass"
        for key in ("current", "baseline", "current_png", "baseline_png", "current_metadata", "baseline_metadata"):
            assert (tmp_path / artifact[key]).exists()
        metadata = yaml.safe_load((tmp_path / artifact["current_metadata"]).read_text(encoding="utf-8"))
        checks = metadata["checks"]
        assert checks["no_horizontal_overflow"] is True
        assert checks["guided_first_viewport"] is True
        assert checks["active_work_cards"] is True
        assert checks["approval_states"] is True


def test_git_native_worker_lane_dogfood_case_exercises_two_lane_recovery(tmp_path: Path) -> None:
    _init_dogfood_repo(tmp_path)

    result = run_dogfood_suite(tmp_path, case_ids=["git-native-worker-lane-hardening"])
    case_result = result["results"][0]

    assert case_result["status"] == "passed"
    assert case_result["score"] == case_result["max_score"]
    assert any("two Git-native lanes reached verified preview state" in lesson for lesson in case_result["lessons"])
    assert any("second lane reported stale recovery after first promotion" in lesson for lesson in case_result["lessons"])
    assert any("cleanup preserved canonical task evidence" in lesson for lesson in case_result["lessons"])
    assert any("devflow task promote " in command["command"] for command in case_result["commands_run"])
    summary_path = next(path for path in case_result["artifacts_created"] if path.endswith("git-native-lane-summary.json"))
    summary = yaml.safe_load((tmp_path / summary_path).read_text(encoding="utf-8"))
    assert summary["first_lane_after_cleanup"]["task_evidence_exists"] is True
    assert summary["first_lane_after_cleanup"]["worktree_exists"] is False
    assert summary["second_lane_after_first_promotion"]["readiness_status"] in {"stale", "blocked"}
    assert summary["second_lane_after_first_promotion"]["next_safe_action"] == "devflow task promote-preview task-0002"


def test_local_worker_lane_dogfood_case_exercises_evidence_ladder(tmp_path: Path) -> None:
    _init_dogfood_repo(tmp_path)

    result = run_dogfood_suite(tmp_path, case_ids=["local-worker-lane-hardening"])
    case_result = result["results"][0]

    assert case_result["status"] == "passed"
    assert case_result["score"] == case_result["max_score"]
    assert any("read-only local worker evidence was summarized" in lesson for lesson in case_result["lessons"])
    assert any("local patch worker evidence reached apply/verify gates" in lesson for lesson in case_result["lessons"])
    assert any("no provider API calls or autonomous routing were introduced" in lesson for lesson in case_result["lessons"])


def test_registry_runtime_contract_dogfood_case_proves_runtime_surfaces(tmp_path: Path) -> None:
    _init_dogfood_repo(tmp_path)

    result = run_dogfood_suite(tmp_path, case_ids=["registry-runtime-contract"])
    case_result = result["results"][0]

    assert case_result["status"] == "passed"
    assert case_result["score"] == case_result["max_score"]
    assert any("list/show runtime contracts exposed run and packet eligibility" in lesson for lesson in case_result["lessons"])
    assert any("remote/provider-backed agent refused before provider execution" in lesson for lesson in case_result["lessons"])
    summary_path = next(path for path in case_result["artifacts_created"] if path.endswith("registry-runtime-contract-summary.json"))
    summary = yaml.safe_load((tmp_path / summary_path).read_text(encoding="utf-8"))
    assert summary["shell_agent_dir"].endswith(".devflow/tasks/task-0001/agents/devflow-shell-worker")
    assert summary["shell_agent_evidence"] == {"packet_json": True, "result_md": True, "worker_log": True}
    assert summary["workspace_file_exists"] is True
    assert summary["root_file_exists"] is False
    assert all(summary["manual_packet_contracts"].values())
    assert summary["remote_runtime_contract"]["task_run_allowed"] is False
    assert summary["remote_runtime_contract"]["packet_allowed"] is True
    assert summary["remote_refusal"] == summary["remote_runtime_contract"]["refusal_reason"]
    assert "task worker execution is not allowed" in summary["remote_refusal"]
    assert summary["provider_api_calls_attempted"] is False


def test_model_audition_dogfood_case_proves_evidence_ladder(tmp_path: Path) -> None:
    _init_dogfood_repo(tmp_path)

    result = run_dogfood_suite(tmp_path, case_ids=["model-audition-evidence"])
    case_result = result["results"][0]

    assert case_result["status"] == "passed"
    assert case_result["score"] == case_result["max_score"]
    assert any("dry-run and execute produced bounded candidate/run evidence" in lesson for lesson in case_result["lessons"])
    assert any("scorecard ranked grounded output first and flagged false claims" in lesson for lesson in case_result["lessons"])
    summary_path = next(path for path in case_result["artifacts_created"] if path.endswith("model-audition-summary.json"))
    summary = yaml.safe_load((tmp_path / summary_path).read_text(encoding="utf-8"))
    assert summary["selected_candidate_count"] == 2
    assert summary["run_count"] == 2
    assert summary["top_profile"] == "local-gemma4-qat"
    assert summary["false_claim_flagged"] is True
    assert summary["task_yaml_unchanged"] is True


def test_simple_scheduler_dogfood_case_exercises_parallel_coordination(tmp_path: Path) -> None:
    _init_dogfood_repo(tmp_path)

    result = run_dogfood_suite(tmp_path, case_ids=["simple-scheduler-parallel-coordination"])
    case_result = result["results"][0]

    assert case_result["status"] == "passed"
    assert case_result["score"] == case_result["max_score"]
    assert any("scheduler exposed ready blocked stale and retry work" in lesson for lesson in case_result["lessons"])
    assert any("retry request preserved prior task evidence" in lesson for lesson in case_result["lessons"])
    assert any("no background scheduler or provider calls were introduced" in lesson for lesson in case_result["lessons"])


def test_question_blocker_resume_loop_dogfood_case(tmp_path: Path) -> None:
    _init_dogfood_repo(tmp_path)

    result = run_dogfood_suite(tmp_path, case_ids=["question-blocker-resume-loop"])
    case_result = result["results"][0]

    assert case_result["status"] == "passed"
    assert case_result["score"] == case_result["max_score"]
    assert any("question list exposed deterministic open blocker" in lesson for lesson in case_result["lessons"])
    assert any("answer preserved source question evidence" in lesson for lesson in case_result["lessons"])
    assert any("no worker resume or provider call was executed by question commands" in lesson for lesson in case_result["lessons"])


def test_operator_readiness_reconciliation_dogfood_case(tmp_path: Path) -> None:
    _init_dogfood_repo(tmp_path)

    result = run_dogfood_suite(tmp_path, case_ids=["operator-readiness-reconciliation"])
    case_result = result["results"][0]

    assert case_result["status"] == "passed"
    assert case_result["score"] == case_result["max_score"]
    assert any("operator surfaces agreed on readiness counts" in lesson for lesson in case_result["lessons"])
    assert any("lifecycle repair outranked stale dispatch guidance" in lesson for lesson in case_result["lessons"])
    assert any("plain descriptive task labels remained primary" in lesson for lesson in case_result["lessons"])


def test_intent_scaffold_dogfood_case_exercises_approval_path(tmp_path: Path) -> None:
    _init_dogfood_repo(tmp_path)

    result = run_dogfood_suite(tmp_path, case_ids=["intent-scaffold-approval-path"])
    case_result = result["results"][0]

    assert case_result["status"] == "passed"
    assert case_result["score"] == case_result["max_score"]
    assert any("intent scaffold wrote review evidence before goal creation" in lesson for lesson in case_result["lessons"])
    assert any("goal creation consumed scaffold task slices without running workers" in lesson for lesson in case_result["lessons"])
    assert any(
        "no provider calls, worker runs, verification, task promotion, commits, or pushes were performed" in lesson
        for lesson in case_result["lessons"]
    )
    summary_path = next(path for path in case_result["artifacts_created"] if path.endswith("intent-scaffold-summary.json"))
    summary = yaml.safe_load((tmp_path / summary_path).read_text(encoding="utf-8"))
    assert summary["idea_id"] == "I-0001"
    assert summary["goal_id"] == "G-0001"
    assert summary["task_slice_ids"] == ["TS-0001", "TS-0002"]
    assert summary["canonical_task_ids"] == []
    assert summary["dry_run_changed_files"] == []


def test_unknown_requested_case_is_skipped_with_reason(tmp_path: Path) -> None:
    _init_dogfood_repo(tmp_path)

    result = run_dogfood_suite(tmp_path, case_ids=["missing-case"])
    case_result = result["results"][0]

    assert case_result["status"] == "skipped"
    assert case_result["score"] == 0
    assert case_result["failure_reason"] == "case not found in suite"
    assert "requested case was not found" in case_result["warnings"][0]


def test_cleanup_failure_is_visible(tmp_path: Path, monkeypatch) -> None:
    _init_dogfood_repo(tmp_path)

    def fake_cleanup(path: Path) -> tuple[bool, str]:
        return False, "cleanup failed for marker"

    monkeypatch.setattr(dogfood, "_cleanup_file", fake_cleanup)

    result = run_dogfood_suite(tmp_path, case_ids=["plan-only-unsafe-git-state"])
    case_result = result["results"][0]

    assert case_result["status"] == "failed"
    assert "cleanup_failed" in case_result["cleanup_status"]
    assert any("cleanup failed" in warning for warning in case_result["warnings"])


def test_cli_commands_and_report_lookup(tmp_path: Path) -> None:
    _init_dogfood_repo(tmp_path)
    old_cwd = Path.cwd()
    try:
        os.chdir(tmp_path)
        listed = runner.invoke(app, ["dogfood", "list"])
        shown = runner.invoke(app, ["dogfood", "show", "unsafe-worker-outcome"])
        run = runner.invoke(app, ["dogfood", "run", "--suite", "production-readiness"])
        score = runner.invoke(app, ["dogfood", "score", "latest"])
        report = runner.invoke(app, ["dogfood", "report", "latest"])
    finally:
        os.chdir(old_cwd)

    assert listed.exit_code == 0, listed.output
    assert "tiny-deterministic-docs-task" in listed.output
    assert shown.exit_code == 0, shown.output
    assert "files_touched with parent traversal fails" in shown.output
    assert run.exit_code == 0, run.output
    assert "silver_met: yes" in run.output
    assert score.exit_code == 0, score.output
    assert "threshold:" in score.output
    assert report.exit_code == 0, report.output
    assert "Boundary Confirmation" in report.output
    assert "devflow release readiness" in report.output


def test_dogfood_command_module_owns_typer_registration() -> None:
    from devflow.control_room.dogfood_command import dogfood_app

    assert {command.name for command in dogfood_app.registered_commands} >= {
        "list",
        "show",
        "run",
        "score",
        "report",
    }


def test_harness_avoids_forbidden_surfaces(tmp_path: Path) -> None:
    _init_dogfood_repo(tmp_path)

    result = run_dogfood_suite(tmp_path, suite="production-readiness")
    commands = [
        str(command["command"]).lower()
        for case_result in result["results"]
        for command in case_result["commands_run"]
    ]
    forbidden_tokens = ["ollama", "openai", "anthropic", "gemini", "push-main", "route"]
    assert not any(token in command for token in forbidden_tokens for command in commands)
    assert not (tmp_path / ".devflow" / "dogfood" / "dashboard").exists()
    assert not (tmp_path / ".devflow" / "dogfood" / "database.sqlite").exists()
    assert not (tmp_path / ".devflow" / "dogfood" / "vector").exists()
