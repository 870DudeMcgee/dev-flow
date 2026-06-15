from __future__ import annotations

from pathlib import Path

from devflow.df_telegram_bridge import run_telegram_to_devflow_pipeline


def test_telegram_bridge_returns_scaffold_pending_action_without_mutation(tmp_path: Path) -> None:
    result = run_telegram_to_devflow_pipeline("build a search plugin", tmp_path)

    assert result["status"] == "pending_approval"
    assert result["pipeline_step"] == "intent_scaffold_pending"
    assert result["goal_id"] is None
    assert result["task_ids"] == []
    assert result["pending_action"]["kind"] == "intent_scaffold"
    assert result["pending_action"]["approval_required"] is True
    assert "devflow idea capture" in result["pending_action"]["approval_commands"][0]
    assert "devflow idea scaffold-goal" in result["pending_action"]["approval_commands"][-1]
    assert "No goals, tasks, workers" in result["telegram_response"]

    assert not (tmp_path / ".devflow" / "goals").exists()
    assert not (tmp_path / ".devflow" / "tasks").exists()
