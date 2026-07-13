from __future__ import annotations

import json
from pathlib import Path

import pytest

from devflow.context_quality import ContextQualityService


def _write_indexes(root: Path) -> None:
    directory = root / ".context-map"
    directory.mkdir()
    (directory / "source-index.json").write_text(json.dumps({"files": [{"path": "src/a.py"}]}))
    (directory / "graphify-freshness.json").write_text(json.dumps({"nodes": 1}))


def test_orient_is_grounded_from_local_indexes_without_model_lane(tmp_path: Path) -> None:
    _write_indexes(tmp_path)
    service = ContextQualityService(lambda root: {"status": "ready", "project": root.name})

    packet = service.orient("trace the decision persistence flow", repo=tmp_path)

    assert packet["status"] == "grounded"
    assert packet["providers"]["context_map"]["status"] == "ready"
    assert packet["providers"]["agent_proxy"]["status"] == "ready"
    assert packet["next_action"]["instruction"] == "Dispatch only anchored, bounded work packets."


def test_orient_blocks_when_local_freshness_evidence_is_missing(tmp_path: Path) -> None:
    service = ContextQualityService(lambda root: {"status": "unavailable"})

    packet = service.orient("trace", repo=tmp_path)

    assert packet["status"] == "blocked"
    assert "Refresh" in packet["next_action"]["instruction"]


@pytest.mark.parametrize("goal", ["", "   ", None])
def test_orient_requires_a_nonblank_goal(tmp_path: Path, goal: object) -> None:
    with pytest.raises(ValueError, match="goal"):
        ContextQualityService().orient(goal, repo=tmp_path)  # type: ignore[arg-type]
