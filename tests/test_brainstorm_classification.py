"""Tests for brainstorm-to-classification gate (RLC-04).

Tests the rule-based classifier, preview builder, pipeline-run attachment,
and server route integration.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from devflow.control_room.brainstorm_pipeline import (
    LOOP_PRESETS,
    ClassificationResult,
    build_classification_preview,
    classify_and_attach_to_run,
    classify_brainstorm_intent,
    write_classification_to_pipeline_run,
)
from devflow.control_room.pipeline_run import (
    create_pipeline_run,
    load_pipeline_run,
)


# ---------------------------------------------------------------------------
# classify_brainstorm_intent — work type
# ---------------------------------------------------------------------------

class TestClassifyWorkType:
    def test_refactor_intent(self):
        result = classify_brainstorm_intent("refactor the auth module to use OAuth2")
        assert result.work_type == "refactor"
        assert "refactor" in result.rationale.lower()
        assert "multi_file_refactor" in result.eligible_presets

    def test_bug_fix_intent(self):
        result = classify_brainstorm_intent("fix the crash when user clicks submit")
        assert result.work_type == "bug_fix"
        assert result.recommended_preset == "bug_fix"

    def test_testing_intent(self):
        result = classify_brainstorm_intent("add unit tests for the parser")
        assert result.work_type == "testing"

    def test_documentation_intent(self):
        result = classify_brainstorm_intent("update the README with new API docs")
        assert result.work_type == "documentation"

    def test_performance_intent(self):
        result = classify_brainstorm_intent("optimize the slow database query latency")
        assert result.work_type == "performance"

    def test_new_feature_intent(self):
        result = classify_brainstorm_intent("implement a new user settings page")
        assert result.work_type == "new_feature"

    def test_review_intent(self):
        result = classify_brainstorm_intent("review and audit the auth flow")
        assert result.work_type == "review"

    def test_cleanup_intent(self):
        result = classify_brainstorm_intent("cleanup unused imports and dead code")
        assert result.work_type == "cleanup"

    def test_general_intent(self):
        result = classify_brainstorm_intent("make the login page better")
        assert result.work_type == "general"
        assert set(result.eligible_presets) == set(LOOP_PRESETS.keys())

    def test_empty_intent(self):
        result = classify_brainstorm_intent("")
        assert result.work_type == "unknown"
        assert result.recommended_preset is None

    def test_none_intent(self):
        result = classify_brainstorm_intent(None)  # type: ignore[arg-type]
        assert result.work_type == "unknown"


# ---------------------------------------------------------------------------
# classify_brainstorm_intent — deterministic-tool eligibility
# ---------------------------------------------------------------------------

class TestClassifyDeterministicTool:
    def test_extract_module_eligible(self):
        result = classify_brainstorm_intent("extract module using tree-sitter")
        assert result.deterministic_tool_eligible is True
        assert result.deterministic_tool_command == "extract_module"
        assert result.recommended_preset is None  # deterministic lane, no preset

    def test_lint_check_eligible(self):
        result = classify_brainstorm_intent("run ruff lint check on all Python files")
        assert result.deterministic_tool_eligible is True
        assert result.deterministic_tool_command == "lint_check"

    def test_test_run_eligible(self):
        result = classify_brainstorm_intent("run pytest on the integration test suite")
        assert result.deterministic_tool_eligible is True
        assert result.deterministic_tool_command == "test_run"

    def test_dependency_scan_eligible(self):
        result = classify_brainstorm_intent("scan the dependency graph for conflicts")
        assert result.deterministic_tool_eligible is True
        assert result.deterministic_tool_command == "dependency_scan"

    def test_not_deterministic(self):
        result = classify_brainstorm_intent("refactor the payment processing module")
        assert result.deterministic_tool_eligible is False
        assert result.deterministic_tool_command is None


# ---------------------------------------------------------------------------
# ClassificationResult model validation
# ---------------------------------------------------------------------------

class TestClassificationResult:
    def test_serialization_roundtrip(self):
        result = ClassificationResult(
            work_type="refactor",
            rationale="test rationale",
            eligible_presets=["multi_file_refactor"],
            recommended_preset="multi_file_refactor",
        )
        data = result.model_dump(mode="json")
        restored = ClassificationResult.model_validate(data)
        assert restored == result

    def test_schema_version_default(self):
        result = classify_brainstorm_intent("some text")
        assert result.schema_version == 1

    def test_all_fields_present(self):
        result = classify_brainstorm_intent("fix the crash")
        data = result.model_dump(mode="json")
        expected_keys = {
            "schema_version",
            "work_type",
            "rationale",
            "deterministic_tool_eligible",
            "deterministic_tool_command",
            "eligible_presets",
            "recommended_preset",
            "why_not_alternatives",
        }
        assert set(data.keys()) == expected_keys


# ---------------------------------------------------------------------------
# build_classification_preview
# ---------------------------------------------------------------------------

class TestClassificationPreview:
    def test_valid_payload(self):
        preview = build_classification_preview(
            {"operator_intent": "refactor the auth module"}
        )
        assert preview["ok"] is True
        assert preview["operator_intent"] == "refactor the auth module"
        assert "classification" in preview
        assert preview["will_write_classification"] is True

    def test_missing_intent_raises(self):
        with pytest.raises(ValueError, match="operator_intent is required"):
            build_classification_preview({})

    def test_empty_intent_raises(self):
        with pytest.raises(ValueError, match="operator_intent is required"):
            build_classification_preview({"operator_intent": "  "})

    def test_non_string_intent_raises(self):
        with pytest.raises(ValueError, match="operator_intent is required"):
            build_classification_preview({"operator_intent": 42})


# ---------------------------------------------------------------------------
# write_classification_to_pipeline_run & classify_and_attach_to_run
# ---------------------------------------------------------------------------

class TestClassificationPipelineRun:
    def test_write_classification_to_run(self, tmp_path: Path):
        run_id = create_pipeline_run(tmp_path, {"source": "test"})
        classification = classify_brainstorm_intent("fix the crash on submit")
        write_classification_to_pipeline_run(tmp_path, run_id, classification)

        run_data = load_pipeline_run(tmp_path, run_id)
        assert "classification.json" in run_data
        cls = run_data["classification.json"]
        assert cls["work_type"] == "bug_fix"
        assert cls["recommended_preset"] == "bug_fix"
        assert cls["schema_version"] == 1

    def test_write_nonexistent_run_raises(self, tmp_path: Path):
        classification = classify_brainstorm_intent("fix crash")
        with pytest.raises(FileNotFoundError, match="Pipeline run not found"):
            write_classification_to_pipeline_run(tmp_path, "nonexistent", classification)

    def test_classify_and_attach_to_run(self, tmp_path: Path):
        run_id = create_pipeline_run(tmp_path, {"source": "test"})
        result = classify_and_attach_to_run(tmp_path, run_id, "refactor the auth module")

        assert result["ok"] is True
        assert result["run_id"] == run_id
        assert "classification" in result
        assert result["classification"]["work_type"] == "refactor"
        assert "classification_path" in result
        assert result["classification_path"].endswith("classification.json")

        # Verify persisted
        run_data = load_pipeline_run(tmp_path, run_id)
        assert run_data["classification.json"]["work_type"] == "refactor"


# ---------------------------------------------------------------------------
# Route payload integration (classify_brainstorm_payload via routes module)
# ---------------------------------------------------------------------------

class TestClassifyRoute:
    def test_classify_without_run_id(self, tmp_path: Path):
        from devflow.control_room.operating_layer_brainstorm_routes import (
            classify_brainstorm_payload,
        )

        result = classify_brainstorm_payload(
            tmp_path,
            {"operator_intent": "implement a new feature for settings"},
        )
        assert result["ok"] is True
        assert result["classification"]["work_type"] == "new_feature"

    def test_classify_with_run_id(self, tmp_path: Path):
        from devflow.control_room.operating_layer_brainstorm_routes import (
            classify_brainstorm_payload,
        )

        run_id = create_pipeline_run(tmp_path, {"source": "test"})
        result = classify_brainstorm_payload(
            tmp_path,
            {"operator_intent": "run lint check", "run_id": run_id},
        )
        assert result["ok"] is True
        assert result["run_id"] == run_id
        assert result["classification"]["deterministic_tool_eligible"] is True

        # Verify persisted in pipeline run
        run_data = load_pipeline_run(tmp_path, run_id)
        assert run_data["classification.json"]["work_type"] != "unknown"

    def test_classify_missing_intent_raises(self, tmp_path: Path):
        from devflow.control_room.brainstorm import BrainstormError
        from devflow.control_room.operating_layer_brainstorm_routes import (
            classify_brainstorm_payload,
        )

        with pytest.raises(BrainstormError, match="operator_intent"):
            classify_brainstorm_payload(tmp_path, {})

    def test_why_not_alternatives_populated(self):
        result = classify_brainstorm_intent("fix the crash")
        assert result.why_not_alternatives
        # Should explain the recommendation
        assert "bug_fix" in result.why_not_alternatives

    def test_why_not_deterministic_lane(self):
        result = classify_brainstorm_intent("extract module from the utils file")
        assert result.deterministic_tool_eligible is True
        assert "deterministic tool" in result.why_not_alternatives.lower()
        assert result.recommended_preset is None
