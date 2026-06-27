from __future__ import annotations

from devflow.control_room.dogfood_command import (
    dogfood_run_exit_code,
    render_dogfood_run_lines,
    run_dogfood_command,
)


def test_render_dogfood_run_lines_owns_cli_summary_sections() -> None:
    result = {
        "run_id": "dogfood-test",
        "run_path": ".devflow/dogfood/runs/dogfood-test/run.yaml",
        "scorecard_path": ".devflow/dogfood/runs/dogfood-test/scorecard.yaml",
        "report_path": ".devflow/dogfood/runs/dogfood-test/report.md",
        "pruned_runs": [".devflow/dogfood/runs/old"],
        "scorecard": {
            "total_score": 80,
            "max_score": 100,
            "threshold_result": {
                "achieved": "bronze",
                "silver_met": False,
            },
            "failures": ["case-a: failed"],
            "warnings": ["case-b: warning"],
        },
    }

    assert render_dogfood_run_lines(result) == (
        "dogfood_run_id: dogfood-test",
        "score: 80/100",
        "threshold: bronze",
        "silver_met: no",
        "run_path: .devflow/dogfood/runs/dogfood-test/run.yaml",
        "scorecard_path: .devflow/dogfood/runs/dogfood-test/scorecard.yaml",
        "report_path: .devflow/dogfood/runs/dogfood-test/report.md",
        "pruned_runs:",
        "  - .devflow/dogfood/runs/old",
        "failures:",
        "  - case-a: failed",
        "warnings:",
        "  - case-b: warning",
    )
    assert dogfood_run_exit_code(result, fail_below_silver=True) == 1
    assert dogfood_run_exit_code(result, fail_below_silver=False) == 0


def test_run_dogfood_command_owns_execution_output(monkeypatch, tmp_path) -> None:
    recorded: dict[str, object] = {}

    def fake_run_dogfood_suite(
        root,
        *,
        suite,
        case_ids,
        write_root_runtime_evidence,
        keep_runs,
    ):
        recorded.update(
            {
                "root": root,
                "suite": suite,
                "case_ids": case_ids,
                "write_root_runtime_evidence": write_root_runtime_evidence,
                "keep_runs": keep_runs,
            }
        )
        return {
            "run_id": "dogfood-test",
            "run_path": ".devflow/dogfood/runs/dogfood-test/run.yaml",
            "scorecard_path": ".devflow/dogfood/runs/dogfood-test/scorecard.yaml",
            "report_path": ".devflow/dogfood/runs/dogfood-test/report.md",
            "pruned_runs": [],
            "scorecard": {
                "total_score": 72,
                "max_score": 100,
                "threshold_result": {
                    "achieved": "bronze",
                    "silver_met": False,
                },
                "failures": [],
                "warnings": [],
            },
        }

    monkeypatch.setattr("devflow.control_room.dogfood_command.run_dogfood_suite", fake_run_dogfood_suite)

    output = run_dogfood_command(
        tmp_path,
        suite="production-readiness",
        case_ids=("case-a",),
        write_root_runtime_evidence=True,
        keep_runs=2,
        fail_below_silver=True,
    )

    assert recorded == {
        "root": tmp_path,
        "suite": "production-readiness",
        "case_ids": ("case-a",),
        "write_root_runtime_evidence": True,
        "keep_runs": 2,
    }
    assert output.exit_code == 1
    assert output.lines == (
        "dogfood_run_id: dogfood-test",
        "score: 72/100",
        "threshold: bronze",
        "silver_met: no",
        "run_path: .devflow/dogfood/runs/dogfood-test/run.yaml",
        "scorecard_path: .devflow/dogfood/runs/dogfood-test/scorecard.yaml",
        "report_path: .devflow/dogfood/runs/dogfood-test/report.md",
    )
