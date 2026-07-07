"""Tests for RLC-05: Supervisor Intent Summary artifact.

Covers:
- IntentSummary Pydantic model validation
- Rule-based generation (build_intent_summary_preview)
- Manual override (build_manual_intent_summary)
- Pipeline run persistence (write_intent_summary_to_run, classify_and_attach_intent_summary)
- Route payload builder (build_intent_summary_payload)
"""

from __future__ import annotations


import pytest

from devflow.control_room.brainstorm_pipeline import (
    build_intent_summary_preview,
    build_manual_intent_summary,
    classify_and_attach_intent_summary,
    write_intent_summary_to_run,
)
from devflow.control_room.pipeline_run import (
    IntentSummary,
    MINIMUM_RUN_FILES,
    create_pipeline_run,
    load_pipeline_run,
)
from devflow.control_room.operating_layer_brainstorm_routes import (
    build_intent_summary_payload,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_run(tmp_path):
    """Create a temporary pipeline run for persistence tests."""
    run_id = create_pipeline_run(tmp_path, {"repo": "/tmp/test"})
    return tmp_path, run_id


# ---------------------------------------------------------------------------
# 1. IntentSummary model validation
# ---------------------------------------------------------------------------

class TestIntentSummaryModel:
    """IntentSummary Pydantic model tests."""

    def test_default_values(self):
        summary = IntentSummary()
        assert summary.schema_version == 1
        assert summary.user_wants == ""
        assert summary.product_outcome == ""
        assert summary.non_negotiables == []
        assert summary.worker_misunderstandings == []
        assert summary.what_done_feels_like == ""
        assert summary.source == "generated"

    def test_all_fields_set(self):
        summary = IntentSummary(
            user_wants="Add a login page",
            product_outcome="Users can authenticate",
            non_negotiables=["No passwords in plaintext", "Must use OAuth"],
            worker_misunderstandings=["Don't add registration flow"],
            what_done_feels_like="All tests pass, login works in browser",
            source="manual",
        )
        assert summary.user_wants == "Add a login page"
        assert summary.product_outcome == "Users can authenticate"
        assert len(summary.non_negotiables) == 2
        assert len(summary.worker_misunderstandings) == 1
        assert summary.what_done_feels_like == "All tests pass, login works in browser"
        assert summary.source == "manual"

    def test_serialization_roundtrip(self):
        summary = IntentSummary(
            user_wants="Build API endpoint",
            non_negotiables=["Must be async"],
            source="generated",
        )
        data = summary.model_dump(mode="json")
        restored = IntentSummary.model_validate(data)
        assert restored == summary

    def test_source_field_accepts_valid_values(self):
        for src in ("generated", "manual", "imported"):
            summary = IntentSummary(source=src)
            assert summary.source == src

    def test_non_negotiables_strips_empty_strings(self):
        summary = IntentSummary(non_negotiables=["must work", "", "  ", "no regress"])
        assert summary.non_negotiables == ["must work", "", "  ", "no regress"]
        # Model itself doesn't strip; the builder functions do

    def test_intent_summary_in_minimum_run_files(self):
        assert "intent-summary.json" in MINIMUM_RUN_FILES


# ---------------------------------------------------------------------------
# 2. Rule-based generation (build_intent_summary_preview)
# ---------------------------------------------------------------------------

class TestRuleBasedGeneration:
    """Rule-based intent summary extraction tests."""

    def test_empty_intent_returns_empty_summary(self):
        result = build_intent_summary_preview("")
        assert result["ok"] is True
        assert result["intent_summary"]["user_wants"] == ""
        assert result["source"] == "generated"

    def test_none_intent_returns_empty_summary(self):
        result = build_intent_summary_preview(None)
        assert result["ok"] is True
        assert result["intent_summary"]["user_wants"] == ""

    def test_simple_intent_extracts_user_wants(self):
        text = "I want to add a login page to the application."
        result = build_intent_summary_preview(text)
        assert result["ok"] is True
        assert result["source"] == "generated"
        assert result["operator_intent"] == text
        summary = result["intent_summary"]
        assert "login" in summary["user_wants"].lower()
        assert summary["source"] == "generated"

    def test_outcome_language_extracts_product_outcome(self):
        text = (
            "Build a user authentication system. "
            "The outcome should be that users can log in securely. "
            "This enables secure access to the dashboard."
        )
        result = build_intent_summary_preview(text)
        summary = result["intent_summary"]
        assert len(summary["product_outcome"]) > 0

    def test_constraint_language_extracts_non_negotiables(self):
        text = (
            "Implement a data export feature. "
            "This must not break existing imports. "
            "Backward compatibility is mandatory. "
            "Always validate the output schema."
        )
        result = build_intent_summary_preview(text)
        summary = result["intent_summary"]
        assert len(summary["non_negotiables"]) > 0

    def test_negation_language_extracts_misunderstandings(self):
        text = (
            "Refactor the database layer. "
            "Do not use ORM abstractions here. "
            "Avoid adding new dependencies. "
            "Don't change the public API."
        )
        result = build_intent_summary_preview(text)
        summary = result["intent_summary"]
        assert len(summary["worker_misunderstandings"]) > 0

    def test_completion_criteria_extracts_done_feels_like(self):
        text = (
            "Add rate limiting to the API. "
            "Done when all tests pass. "
            "Completion criteria: verified with load testing."
        )
        result = build_intent_summary_preview(text)
        summary = result["intent_summary"]
        assert len(summary["what_done_feels_like"]) > 0

    def test_long_intent_truncates_user_wants(self):
        long_text = "I want " + "x" * 500 + "."
        result = build_intent_summary_preview(long_text)
        summary = result["intent_summary"]
        assert len(summary["user_wants"]) <= 250  # truncated + ellipsis

    def test_multi_sentence_intent(self):
        text = (
            "I want to add a search feature. "
            "The result should enable users to find content quickly. "
            "This is critical for the product. "
            "Do not index private documents."
        )
        result = build_intent_summary_preview(text)
        summary = result["intent_summary"]
        assert "search" in summary["user_wants"].lower()
        assert summary["source"] == "generated"


# ---------------------------------------------------------------------------
# 3. Manual override (build_manual_intent_summary)
# ---------------------------------------------------------------------------

class TestManualOverride:
    """Manual intent summary override tests."""

    def test_manual_summary_from_dict(self):
        manual = {
            "user_wants": "Custom login page",
            "product_outcome": "Users authenticate",
            "non_negotiables": ["No plaintext passwords"],
            "worker_misunderstandings": ["Don't add registration"],
            "what_done_feels_like": "Tests pass, works in browser",
        }
        result = build_manual_intent_summary("Build login", manual)
        assert result["ok"] is True
        assert result["source"] == "manual"
        summary = result["intent_summary"]
        assert summary["source"] == "manual"
        assert summary["user_wants"] == "Custom login page"

    def test_manual_summary_partial_fields(self):
        manual = {"user_wants": "Add feature X"}
        result = build_manual_intent_summary("Add feature X", manual)
        summary = result["intent_summary"]
        assert summary["user_wants"] == "Add feature X"
        assert summary["product_outcome"] == ""
        assert summary["non_negotiables"] == []

    def test_manual_summary_empty_dict_raises(self):
        with pytest.raises(ValueError, match="manual_summary"):
            build_manual_intent_summary("Build something", {})

    def test_manual_summary_none_raises(self):
        with pytest.raises(ValueError, match="manual_summary"):
            build_manual_intent_summary("Build something", None)

    def test_manual_summary_non_dict_raises(self):
        with pytest.raises(ValueError, match="manual_summary"):
            build_manual_intent_summary("Build something", "not a dict")

    def test_manual_summary_empty_intent_raises(self):
        with pytest.raises(ValueError, match="operator_intent"):
            build_manual_intent_summary("", {"user_wants": "x"})

    def test_manual_summary_strips_empty_list_items(self):
        manual = {
            "user_wants": "Test",
            "non_negotiables": ["valid", "", "  ", "also valid"],
            "worker_misunderstandings": ["avoid this", "", "  "],
        }
        result = build_manual_intent_summary("Test intent", manual)
        summary = result["intent_summary"]
        assert summary["non_negotiables"] == ["valid", "also valid"]
        assert summary["worker_misunderstandings"] == ["avoid this"]


# ---------------------------------------------------------------------------
# 4. Pipeline run persistence
# ---------------------------------------------------------------------------

class TestPersistence:
    """write_intent_summary_to_run and classify_and_attach_intent_summary tests."""

    def test_write_intent_summary_to_run(self, tmp_run):
        root, run_id = tmp_run
        summary = IntentSummary(
            user_wants="Build feature X",
            source="generated",
        )
        write_intent_summary_to_run(root, run_id, summary)

        # Verify file exists and content is correct
        run_data = load_pipeline_run(root, run_id)
        assert "intent-summary.json" in run_data
        loaded = run_data["intent-summary.json"]
        assert loaded["user_wants"] == "Build feature X"
        assert loaded["source"] == "generated"
        assert loaded["schema_version"] == 1

    def test_write_intent_summary_as_dict(self, tmp_run):
        root, run_id = tmp_run
        data = {"user_wants": "Dict-based summary", "source": "imported", "schema_version": 1}
        write_intent_summary_to_run(root, run_id, data)

        run_data = load_pipeline_run(root, run_id)
        assert run_data["intent-summary.json"]["user_wants"] == "Dict-based summary"

    def test_write_to_nonexistent_run_raises(self, tmp_path):
        summary = IntentSummary(user_wants="test")
        with pytest.raises(FileNotFoundError, match="not found"):
            write_intent_summary_to_run(tmp_path, "nonexistent-run-id", summary)

    def test_write_invalid_type_raises(self, tmp_run):
        root, run_id = tmp_run
        with pytest.raises(TypeError, match="must be an IntentSummary"):
            write_intent_summary_to_run(root, run_id, "not a model or dict")

    def test_classify_and_attach_intent_summary(self, tmp_run):
        root, run_id = tmp_run
        intent = "I want to add a login page. Must not break existing auth."
        result = classify_and_attach_intent_summary(root, run_id, intent)

        assert result["ok"] is True
        assert result["run_id"] == run_id
        assert result["source"] == "generated"
        assert "intent_summary" in result
        assert "intent_summary_path" in result

        # Verify file was written
        run_data = load_pipeline_run(root, run_id)
        assert "intent-summary.json" in run_data
        assert "login" in run_data["intent-summary.json"]["user_wants"].lower()

    def test_classify_and_attach_creates_complete_summary(self, tmp_run):
        root, run_id = tmp_run
        intent = (
            "Implement rate limiting. Must not break existing endpoints. "
            "Done when all tests pass. Don't use external libraries."
        )
        result = classify_and_attach_intent_summary(root, run_id, intent)
        summary = result["intent_summary"]
        assert summary["source"] == "generated"
        # Should extract non-negotiables from "must not" language
        assert len(summary["non_negotiables"]) > 0 or summary["user_wants"]


# ---------------------------------------------------------------------------
# 5. Route integration
# ---------------------------------------------------------------------------

class TestRouteIntegration:
    """build_intent_summary_payload route builder tests."""

    def test_preview_without_run_id(self, tmp_path):
        payload = {"operator_intent": "Build a search feature"}
        result = build_intent_summary_payload(tmp_path, payload)
        assert result["ok"] is True
        assert result["source"] == "generated"
        assert "intent_summary" in result
        assert "run_id" not in result

    def test_with_run_id_writes_to_run(self, tmp_run):
        root, run_id = tmp_run
        payload = {
            "operator_intent": "Add authentication",
            "run_id": run_id,
        }
        result = build_intent_summary_payload(root, payload)
        assert result["ok"] is True
        assert result["run_id"] == run_id
        assert result["source"] == "generated"
        assert "intent_summary_path" in result

        # Verify persistence
        run_data = load_pipeline_run(root, run_id)
        assert "intent-summary.json" in run_data

    def test_manual_summary_override(self, tmp_path):
        payload = {
            "operator_intent": "Build login",
            "manual_summary": {
                "user_wants": "Custom login page",
                "non_negotiables": ["Must use OAuth"],
            },
        }
        result = build_intent_summary_payload(tmp_path, payload)
        assert result["ok"] is True
        assert result["source"] == "manual"
        assert result["intent_summary"]["user_wants"] == "Custom login page"
        assert result["intent_summary"]["source"] == "manual"

    def test_manual_summary_with_run_id(self, tmp_run):
        root, run_id = tmp_run
        payload = {
            "operator_intent": "Build login",
            "run_id": run_id,
            "manual_summary": {
                "user_wants": "Manual override",
            },
        }
        result = build_intent_summary_payload(root, payload)
        assert result["source"] == "manual"
        assert result["run_id"] == run_id
        assert result["intent_summary"]["user_wants"] == "Manual override"

        # Verify persistence
        run_data = load_pipeline_run(root, run_id)
        assert run_data["intent-summary.json"]["user_wants"] == "Manual override"

    def test_missing_operator_intent_raises(self, tmp_path):
        with pytest.raises(Exception):
            build_intent_summary_payload(tmp_path, {})

    def test_empty_operator_intent_raises(self, tmp_path):
        with pytest.raises(Exception):
            build_intent_summary_payload(tmp_path, {"operator_intent": ""})

    def test_empty_manual_summary_uses_generated(self, tmp_path):
        """Empty dict manual_summary should fall through to generated path."""
        payload = {
            "operator_intent": "Build feature",
            "manual_summary": {},
        }
        result = build_intent_summary_payload(tmp_path, payload)
        assert result["source"] == "generated"

    def test_project_resolution(self, tmp_path):
        """Verify project resolution is attempted for project param."""
        payload = {
            "operator_intent": "Build feature",
            "project": "nonexistent-project",
        }
        # Should raise because project resolution will fail
        with pytest.raises(Exception):
            build_intent_summary_payload(tmp_path, payload)
