from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from devflow.control_room.models import TaskRecord
from devflow.control_room.paths import relative_path, task_dir


PATCH_WORKER_NEXT_ACTIONS = {
    "needs_review": "devflow task review-patch {task_id} --agent {worker_id}",
    "needs_dry_run": "devflow task patch-dry-run {task_id} --agent {worker_id}",
    "needs_apply": "devflow task apply-patch {task_id} --agent {worker_id}",
    "needs_verification": 'devflow task verify {task_id} --shell "<command>"',
    "needs_promotion_preview": "devflow task promote-preview {task_id}",
    "ready": "devflow task promote {task_id}",
    "failed": "devflow task escalation-packet {task_id} --agent {worker_id}",
}


def local_worker_lane_summary(root: Path, task: TaskRecord, worker_id: str | None = None) -> dict[str, Any] | None:
    base = task_dir(root, task.id)
    patch_summary = _latest_patch_worker_summary(root, base, task, worker_id)
    pool_summary = _latest_worker_pool_summary(root, base, task, worker_id)
    if patch_summary and pool_summary:
        return patch_summary if patch_summary["generated_at_sort"] >= pool_summary["generated_at_sort"] else pool_summary
    return patch_summary or pool_summary


def _latest_patch_worker_summary(root: Path, base: Path, task: TaskRecord, worker_id: str | None) -> dict[str, Any] | None:
    agents_dir = base / "agents"
    if not agents_dir.is_dir():
        return None
    candidates = [agents_dir / worker_id] if worker_id else sorted(path for path in agents_dir.iterdir() if path.is_dir())
    runs: list[tuple[str, Path, dict[str, Any]]] = []
    for run_dir in candidates:
        run_json, error = _read_run_json(run_dir / "run.json")
        if error:
            run_json = {
                "agent_id": run_dir.name,
                "status": "failed",
                "proposal_patch_found": False,
                "summary": error,
            }
        if run_json:
            runs.append((_sort_value(run_json), run_dir, run_json))
    if not runs:
        return None
    _, run_dir, run_json = sorted(runs, key=lambda item: item[0])[-1]
    resolved_worker = str(run_json.get("agent_id") or run_json.get("worker_id") or run_dir.name)
    readiness = _patch_readiness(base, task, run_dir, run_json)
    evidence_paths = _existing_paths(
        root,
        [
            run_dir / "run.json",
            run_dir / "proposal.patch",
            run_dir / "result.md",
            run_dir / "logs" / "worker.log",
            base / "local-model-runs",
            base / "patch-application.json",
            base / "verification.json",
            run_dir / "escalation-packet.md",
        ],
    )
    return {
        "schema": 1,
        "task_id": task.id,
        "lane_type": "local-patch-worker",
        "profile_id": resolved_worker,
        "worker_id": resolved_worker,
        "model": run_json.get("model"),
        "adapter": run_json.get("adapter"),
        "permission_mode": "workspace_write",
        "latest_run_id": run_dir.name,
        "latest_status": str(run_json.get("status") or "unknown"),
        "patch_candidate": bool(run_json.get("proposal_patch_found") and (run_dir / "proposal.patch").exists()),
        "patch_review_status": readiness.get("patch_review_status"),
        "patch_dry_run_status": readiness.get("patch_dry_run_status"),
        "patch_application_status": readiness.get("patch_application_status"),
        "verification_status": task.verification_status,
        "promotion_readiness": readiness.get("promotion_readiness"),
        "readiness_status": readiness["status"],
        "readiness_errors": readiness["errors"],
        "readiness_warnings": readiness["warnings"],
        "evidence_paths": evidence_paths,
        "next_safe_action": _next_action(task.id, resolved_worker, readiness["status"]),
        "generated_at_sort": _sort_value(run_json),
    }


def _latest_worker_pool_summary(root: Path, base: Path, task: TaskRecord, worker_id: str | None) -> dict[str, Any] | None:
    runs_dir = base / "local-model-runs"
    if not runs_dir.is_dir():
        return None
    candidates = sorted(path for path in runs_dir.iterdir() if path.is_dir())
    runs: list[tuple[str, Path, dict[str, Any]]] = []
    for run_dir in candidates:
        run_json, error = _read_run_json(run_dir / "run.json")
        if error:
            run_json = {
                "profile_id": run_dir.name,
                "worker_id": run_dir.name,
                "status": "failed",
                "error_message": error,
            }
        if run_json and (worker_id is None or run_json.get("worker_id") == worker_id or run_json.get("profile_id") == worker_id):
            runs.append((_sort_value(run_json), run_dir, run_json))
    if not runs:
        return None
    _, run_dir, run_json = sorted(runs, key=lambda item: item[0])[-1]
    status = str(run_json.get("status") or "unknown")
    readiness = "failed" if status == "failed" else "low_quality" if status == "low_quality" else "needs_review"
    resolved_worker = str(run_json.get("worker_id") or run_json.get("profile_id") or run_dir.name)
    return {
        "schema": 1,
        "task_id": task.id,
        "lane_type": "local-model-worker-pool",
        "profile_id": run_json.get("profile_id"),
        "worker_id": resolved_worker,
        "model": run_json.get("model"),
        "adapter": run_json.get("adapter"),
        "permission_mode": run_json.get("permission_mode") or "read_only",
        "latest_run_id": run_dir.name,
        "latest_status": status,
        "patch_candidate": False,
        "patch_review_status": None,
        "patch_dry_run_status": None,
        "patch_application_status": None,
        "verification_status": task.verification_status,
        "promotion_readiness": None,
        "readiness_status": readiness,
        "readiness_errors": [str(run_json.get("error_message") or "local worker failed")] if status == "failed" else [],
        "readiness_warnings": [str(run_json.get("quality_notes") or "local worker output is low quality")] if status == "low_quality" else [],
        "evidence_paths": _existing_paths(
            root,
            [
                run_dir / "run.json",
                run_dir / "packet.md",
                run_dir / "response.md",
                run_dir / "raw_output.txt",
                run_dir / "error.txt",
            ],
        ),
        "next_safe_action": f"devflow agent evidence {task.id} --json",
        "generated_at_sort": _sort_value(run_json),
    }


def _patch_readiness(base: Path, task: TaskRecord, run_dir: Path, run_json: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    if run_json.get("status") in {"failed", "error"}:
        return {"status": "failed", "errors": [str(run_json.get("summary") or "local patch worker failed")], "warnings": warnings}
    if not (run_json.get("proposal_patch_found") and (run_dir / "proposal.patch").exists()):
        return {"status": "failed", "errors": ["proposal.patch is missing"], "warnings": warnings}
    review = _latest_json(base / "local-model-runs", "patch-review.json")
    if not review:
        return {"status": "needs_review", "errors": errors, "warnings": warnings}
    dry_run = _latest_json(base / "local-model-runs", "patch-dry-run.json")
    if not dry_run:
        return {"status": "needs_dry_run", "errors": errors, "warnings": warnings, "patch_review_status": review.get("review_status")}
    application = _read_json_object(base / "patch-application.json")
    if not application:
        return {
            "status": "needs_apply",
            "errors": errors,
            "warnings": warnings,
            "patch_review_status": review.get("review_status"),
            "patch_dry_run_status": dry_run.get("dry_run_status"),
        }
    if task.verification_status != "passed":
        return {
            "status": "needs_verification",
            "errors": errors,
            "warnings": warnings,
            "patch_review_status": review.get("review_status"),
            "patch_dry_run_status": dry_run.get("dry_run_status"),
            "patch_application_status": application.get("status") or application.get("application_status"),
        }
    promotion = _read_json_object(base / "promotion-preview.json")
    promotion_readiness = promotion.get("promotion_readiness") if promotion else None
    status = "ready" if promotion_readiness == "ready" else "needs_promotion_preview"
    return {
        "status": status,
        "errors": errors,
        "warnings": warnings,
        "patch_review_status": review.get("review_status"),
        "patch_dry_run_status": dry_run.get("dry_run_status"),
        "patch_application_status": application.get("status") or application.get("application_status"),
        "promotion_readiness": promotion_readiness,
    }


def _next_action(task_id: str, worker_id: str, status: str) -> str:
    return PATCH_WORKER_NEXT_ACTIONS.get(status, "devflow task show {task_id}").format(task_id=task_id, worker_id=worker_id)


def _read_json_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _read_run_json(path: Path) -> tuple[dict[str, Any], str | None]:
    if not path.exists():
        return {}, None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {}, f"invalid run.json: {exc.msg}"
    except OSError as exc:
        return {}, f"unreadable run.json: {exc}"
    if not isinstance(payload, dict):
        return {}, "invalid run.json: root must be an object"
    return payload, None


def _latest_json(parent: Path, name: str) -> dict[str, Any]:
    if not parent.is_dir():
        return {}
    matches = sorted(path for path in parent.glob(f"*/{name}") if path.is_file())
    return _read_json_object(matches[-1]) if matches else {}


def _existing_paths(root: Path, paths: list[Path]) -> list[str]:
    found: list[str] = []
    for path in paths:
        if path.is_file():
            found.append(relative_path(root, path))
        elif path.is_dir():
            found.extend(relative_path(root, child) for child in sorted(path.rglob("*")) if child.is_file())
    return sorted(dict.fromkeys(found))


def _sort_value(payload: dict[str, Any]) -> str:
    return str(payload.get("finished_at") or payload.get("updated_at") or payload.get("started_at") or payload.get("run_id") or "")
