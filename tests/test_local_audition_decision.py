from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from devflow.loop.local_audition_decision import (
    build_pending_human_decision,
    build_pending_human_decision_from_audition,
    human_decision_paths,
    persist_human_decision,
    render_human_decision_markdown,
)


def _role_results() -> list[dict]:
    return [
        {
            "role": "planner",
            "candidate_id": "candidate-a",
            "disposition": "recommended",
            "qualification_status": "qualified",
            "qualification_gates": {
                "scorecard": True,
                "reliability": True,
                "three_repeat_evidence": True,
                "independent_review": True,
            },
            "reliability": {"eligible": True, "reasons": []},
            "metrics": {
                "quality": 92.0,
                "consistency": 100.0,
                "mean_duration_seconds": 1.25,
                "mean_total_tokens": 240.0,
            },
        },
        {
            "role": "builder",
            "candidate_id": "candidate-b",
            "disposition": "ineligible",
            "qualification_status": "provisional",
            "qualification_gates": {
                "scorecard": False,
                "reliability": False,
                "three_repeat_evidence": True,
                "independent_review": True,
            },
            "reliability": {
                "eligible": False,
                "reasons": ["critical_false_accept"],
            },
            "metrics": {
                "quality": 99.0,
                "consistency": 100.0,
                "mean_duration_seconds": 0.5,
                "mean_total_tokens": 100.0,
            },
        },
    ]


def _record() -> dict:
    return build_pending_human_decision(
        run_id="run-001",
        proposed_role_mappings={"planner": "candidate-a"},
        role_results=_role_results(),
        evidence_fingerprints=["artifact-a:runtime-a", "review-a"],
        verification_commands=[
            "PYTHONPATH=src .venv/bin/python -m pytest -q tests/test_local_audition_decision.py",
            "PYTHONPATH=src .venv/bin/python -m devflow.cli loop spine-fixture --json",
        ],
        approval_patch="*** Begin Patch\n*** Update File: src/devflow/loop/profiles.yaml\n*** End Patch",
        rollback_patch="*** Begin Patch\n*** Update File: src/devflow/loop/profiles.yaml\n*** End Patch",
        remaining_risks=["The approved mapping still requires a real M1 route check."],
    )


def test_builds_pending_record_with_exact_profile_targets() -> None:
    record = _record()

    assert record["schema_version"] == 1
    assert record["status"] == "pending"
    assert record["approved_at"] is None
    assert record["no_profile_changes_applied"] is True
    assert record["proposed_role_mappings"] == {"planner": "candidate-a"}
    assert record["profile_targets"] == {
        "planner": (
            "src/devflow/loop/profiles.yaml::"
            "profiles.mini-baseline.roles.planner"
        )
    }
    assert record["role_results"] == _role_results()


def test_recommended_mapping_requires_fully_qualified_independent_evidence() -> None:
    for gate in (
        "scorecard",
        "reliability",
        "three_repeat_evidence",
        "independent_review",
    ):
        results = _role_results()
        results[0]["qualification_gates"][gate] = False

        with pytest.raises(ValueError, match=gate):
            build_pending_human_decision(
                run_id="run-001",
                proposed_role_mappings={"planner": "candidate-a"},
                role_results=results,
                evidence_fingerprints=["evidence-a"],
                verification_commands=["pytest -q"],
                approval_patch="approval patch",
                rollback_patch="rollback patch",
                remaining_risks=["risk"],
            )


def test_rejects_duplicate_fingerprints_and_unsafe_run_ids() -> None:
    kwargs = {
        "proposed_role_mappings": {"planner": "candidate-a"},
        "role_results": _role_results(),
        "verification_commands": ["pytest -q"],
        "approval_patch": "approval patch",
        "rollback_patch": "rollback patch",
        "remaining_risks": ["risk"],
    }
    with pytest.raises(ValueError, match="evidence_fingerprints"):
        build_pending_human_decision(
            run_id="run-001",
            evidence_fingerprints=["same", "same"],
            **kwargs,
        )
    with pytest.raises(ValueError, match="run_id"):
        build_pending_human_decision(
            run_id="../escape",
            evidence_fingerprints=["evidence-a"],
            **kwargs,
        )


def test_markdown_is_explicitly_pending_and_complete() -> None:
    markdown = render_human_decision_markdown(_record())

    for text in (
        "# Pending Human Decision",
        "NO PROFILE CHANGES APPLIED",
        "planner -> candidate-a",
        "builder / candidate-b: INELIGIBLE",
        "Reliability",
        "Quality",
        "Consistency",
        "Duration",
        "Token use",
        "profiles.mini-baseline.roles.planner",
        "First approval patch",
        "Remaining risks",
        "Rollback patch",
    ):
        assert text in markdown


def test_persists_atomic_write_once_json_markdown_pair(tmp_path: Path) -> None:
    record = _record()
    json_path, markdown_path = persist_human_decision(tmp_path, record)

    assert (json_path, markdown_path) == human_decision_paths(tmp_path, "run-001")
    assert json.loads(json_path.read_text()) == record
    assert markdown_path.read_text() == render_human_decision_markdown(record)
    assert list(json_path.parent.glob("*.tmp")) == []
    with pytest.raises(FileExistsError):
        persist_human_decision(tmp_path, record)
    assert json.loads(json_path.read_text()) == record
    assert markdown_path.read_text() == render_human_decision_markdown(record)


def test_second_publish_failure_rolls_back_only_new_json(tmp_path: Path) -> None:
    calls = 0

    def fail_second(source: Path, target: Path) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("markdown publish failed")
        os.link(source, target)

    with pytest.raises(OSError, match="markdown publish failed"):
        persist_human_decision(tmp_path, _record(), commit=fail_second)

    json_path, markdown_path = human_decision_paths(tmp_path, "run-001")
    assert not json_path.exists()
    assert not markdown_path.exists()
    assert list(json_path.parent.glob("*.tmp")) == []


@pytest.mark.parametrize("existing_kind", ["json", "markdown"])
def test_matching_single_file_orphan_is_recovered(
    tmp_path: Path, existing_kind: str
) -> None:
    record = _record()
    json_path, markdown_path = human_decision_paths(tmp_path, "run-001")
    json_path.parent.mkdir(parents=True)
    if existing_kind == "json":
        json_path.write_text(
            json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        )
    else:
        markdown_path.write_text(render_human_decision_markdown(record))

    assert persist_human_decision(tmp_path, record) == (json_path, markdown_path)
    assert json.loads(json_path.read_text()) == record
    assert markdown_path.read_text() == render_human_decision_markdown(record)


def test_conflicting_single_file_orphan_is_never_removed(tmp_path: Path) -> None:
    json_path, markdown_path = human_decision_paths(tmp_path, "run-001")
    json_path.parent.mkdir(parents=True)
    json_path.write_text("conflicting user evidence\n")

    with pytest.raises(FileExistsError):
        persist_human_decision(tmp_path, _record())

    assert json_path.read_text() == "conflicting user evidence\n"
    assert not markdown_path.exists()


def test_persistence_does_not_modify_profiles_yaml(tmp_path: Path) -> None:
    profiles = Path(__file__).parents[1] / "src/devflow/loop/profiles.yaml"
    before = hashlib.sha256(profiles.read_bytes()).hexdigest()

    persist_human_decision(tmp_path, _record())

    assert hashlib.sha256(profiles.read_bytes()).hexdigest() == before


def test_builds_pending_record_from_rankings_and_qualification_outputs() -> None:
    ranking = {
        "role": "planner",
        "ranked": [{
            "candidate_id": "candidate-a",
            "artifact_fingerprint": "artifact-a",
            "runtime_fingerprint": "runtime-a",
            "quality": 92.0,
            "repeat_consistency": 99.0,
            "mean_duration_seconds": 1.25,
            "mean_total_tokens": 240.0,
        }],
        "ineligible": [{
            "candidate_id": "candidate-b",
            "artifact_fingerprint": "artifact-b",
            "runtime_fingerprint": "runtime-b",
            "reasons": ["identity_drift"],
        }],
    }
    qualification = {
        "model": "candidate-a",
        "role": "planner",
        "status": "qualified",
        "qualification_gates": {
            "scorecard": True,
            "reliability": True,
            "three_repeat_evidence": True,
            "independent_review": True,
        },
        "blocking_reasons": [],
    }

    record = build_pending_human_decision_from_audition(
        run_id="run-assembly",
        rankings=[ranking],
        qualifications=[qualification],
        verification_commands=["pytest -q tests/test_local_audition_decision.py"],
        approval_patch="approval patch",
        rollback_patch="rollback patch",
        remaining_risks=["real M1 route check remains required"],
    )

    assert record["proposed_role_mappings"] == {"planner": "candidate-a"}
    assert record["evidence_fingerprints"] == [
        "artifact-a:runtime-a", "artifact-b:runtime-b"
    ]
    assert record["role_results"][0]["disposition"] == "recommended"
    assert record["role_results"][1]["disposition"] == "ineligible"


def test_second_publish_that_creates_then_raises_rolls_back_its_pair(tmp_path: Path) -> None:
    calls = 0

    def create_then_raise(source: Path, target: Path) -> None:
        nonlocal calls
        calls += 1
        os.link(source, target)
        if calls == 2:
            raise OSError("late markdown publish failure")

    with pytest.raises(OSError, match="late markdown publish failure"):
        persist_human_decision(tmp_path, _record(), commit=create_then_raise)

    json_path, markdown_path = human_decision_paths(tmp_path, "run-001")
    assert not json_path.exists()
    assert not markdown_path.exists()
