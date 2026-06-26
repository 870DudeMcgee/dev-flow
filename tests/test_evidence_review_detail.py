from __future__ import annotations

import json
from pathlib import Path

from devflow.control_room.evidence_review_detail import build_evidence_review_detail
from devflow.control_room.service import create_task, run_shell_task
from devflow.control_room.status_projection import build_task_status_projection


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _write_patch_agent_evidence(root: Path, task_id: str) -> None:
    agent_dir = root / ".devflow" / "tasks" / task_id / "agents" / "qwopus-implementer"
    agent_dir.mkdir(parents=True, exist_ok=True)
    (agent_dir / "proposal.patch").write_text("diff --git a/agent.txt b/agent.txt\n", encoding="utf-8")
    (agent_dir / "result.md").write_text("Patch agent result\n", encoding="utf-8")
    _write_json(
        agent_dir / "run.json",
        {
            "schema_version": 1,
            "task_id": task_id,
            "agent_id": "qwopus-implementer",
            "status": "complete",
            "model": "qwopus:latest",
            "adapter": "ollama_chat",
            "proposal_patch_found": True,
        },
    )


def _write_local_model_patch_evidence(root: Path, task_id: str) -> None:
    run_dir = root / ".devflow" / "tasks" / task_id / "local-model-runs" / "agent-qwopus-implementer"
    run_dir.mkdir(parents=True, exist_ok=True)
    proposal_rel = f".devflow/tasks/{task_id}/local-model-runs/agent-qwopus-implementer/proposal.patch"
    review_rel = f".devflow/tasks/{task_id}/local-model-runs/agent-qwopus-implementer/patch-review.json"
    (run_dir / "proposal.patch").write_text("diff --git a/review-only.py b/review-only.py\n", encoding="utf-8")
    (run_dir / "response.md").write_text("Model response with patch candidate\n", encoding="utf-8")
    (run_dir / "patch-review.md").write_text("# Patch review\n", encoding="utf-8")
    (run_dir / "patch-dry-run.md").write_text("# Patch dry-run\n", encoding="utf-8")
    _write_json(
        run_dir / "run.json",
        {
            "schema_version": 1,
            "task_id": task_id,
            "run_id": "agent-qwopus-implementer",
            "worker_id": "qwopus-implementer",
            "profile_id": "qwopus-local",
            "status": "complete",
            "model": "qwopus:latest",
            "adapter": "ollama_chat",
            "permission_mode": "workspace_write",
        },
    )
    _write_json(
        run_dir / "patch-review.json",
        {
            "schema_version": 1,
            "task_id": task_id,
            "run_id": "agent-qwopus-implementer",
            "patch_path": proposal_rel,
            "review_status": "low_risk_candidate",
            "risk": "low",
            "files_touched": ["review-only.py"],
        },
    )
    _write_json(
        run_dir / "patch-dry-run.json",
        {
            "schema_version": 1,
            "task_id": task_id,
            "run_id": "agent-qwopus-implementer",
            "proposal_patch_path": proposal_rel,
            "patch_review_path": review_rel,
            "dry_run_status": "would_apply_cleanly",
            "risk": "low",
            "files_checked": ["review-only.py"],
            "files_would_create": ["created-by-dry-run.py"],
            "files_would_modify": ["modified-by-dry-run.py"],
            "files_would_delete": ["deleted-by-dry-run.py"],
            "hunks_matched": 1,
            "hunks_failed": 0,
        },
    )


def test_evidence_review_detail_collects_operator_facing_evidence_and_changed_files(
    tmp_path: Path,
) -> None:
    task = create_task(tmp_path, "review evidence detail")
    run_shell_task(tmp_path, task.id, ["/bin/sh", "-c", "printf 'worker output\\n' > result.txt"])
    task_path = tmp_path / ".devflow" / "tasks" / task.id
    verification_path = task_path / "verification.json"
    verification_path.unlink()
    _write_patch_agent_evidence(tmp_path, task.id)
    _write_local_model_patch_evidence(tmp_path, task.id)
    _write_json(
        task_path / "promotion-preview.json",
        {
            "schema_version": 1,
            "task_id": task.id,
            "promotion_readiness": "blocked",
            "changed_files": ["preview-changed.py"],
            "added": ["preview-added.py"],
            "modified": ["preview-modified.py"],
            "deleted": ["preview-deleted.py"],
            "untracked": ["preview-untracked.py"],
            "binary": ["preview-binary.bin"],
            "renamed": [{"from": "old-name.py", "to": "new-name.py"}],
        },
    )

    projection = build_task_status_projection(tmp_path, task.id)
    detail = build_evidence_review_detail(tmp_path, projection)

    assert detail.schema_version == 1
    assert detail.task_id == task.id
    assert detail.title == "review evidence detail"
    assert f".devflow/tasks/{task.id}/task.yaml" in detail.evidence_paths
    assert f".devflow/tasks/{task.id}/events.jsonl" in detail.evidence_paths
    assert f".devflow/tasks/{task.id}/agents/qwopus-implementer/proposal.patch" in detail.evidence_paths
    assert f".devflow/tasks/{task.id}/local-model-runs/agent-qwopus-implementer/proposal.patch" in detail.evidence_paths
    assert f".devflow/tasks/{task.id}/local-model-runs/agent-qwopus-implementer/patch-review.md" in detail.evidence_paths
    assert f".devflow/tasks/{task.id}/local-model-runs/agent-qwopus-implementer/patch-dry-run.md" in detail.evidence_paths
    assert f".devflow/tasks/{task.id}/verification.json" in detail.missing_evidence
    assert detail.patch_review_path == (
        f".devflow/tasks/{task.id}/local-model-runs/agent-qwopus-implementer/patch-review.md"
    )
    assert detail.patch_dry_run_path == (
        f".devflow/tasks/{task.id}/local-model-runs/agent-qwopus-implementer/patch-dry-run.md"
    )
    assert detail.promotion_preview_path == f".devflow/tasks/{task.id}/promotion-preview.json"
    assert detail.proposal_patch_paths == [
        f".devflow/tasks/{task.id}/agents/qwopus-implementer/proposal.patch",
        f".devflow/tasks/{task.id}/local-model-runs/agent-qwopus-implementer/proposal.patch",
    ]
    assert detail.changed_files == [
        "created-by-dry-run.py",
        "deleted-by-dry-run.py",
        "modified-by-dry-run.py",
        "new-name.py",
        "preview-added.py",
        "preview-binary.bin",
        "preview-changed.py",
        "preview-deleted.py",
        "preview-modified.py",
        "preview-untracked.py",
        "result.txt",
        "review-only.py",
    ]

    artifact_kinds = {artifact.kind for artifact in detail.artifacts}
    assert "result" in artifact_kinds
    assert "patch proposal" in artifact_kinds
    assert "model run" in artifact_kinds
    assert "model response" in artifact_kinds
    assert "agent result" in artifact_kinds
    assert "patch review" in artifact_kinds
    assert "patch dry-run" in artifact_kinds
    assert detail.operator_summary
    assert len(detail.operator_summary) <= 140
