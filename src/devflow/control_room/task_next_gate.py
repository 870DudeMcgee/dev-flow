"""Canonical task-next-gate resolver.

Fixes the split-brain: existing Qwopus patch-evidence knows the next gate is
``review-patch``, but visible status projections skip to ``verify``.  All
consumers (status_projection, review_readiness, task_workbench, operating_layer)
must agree on this canonical gate so the UI drives operators through the full
patch ladder before showing verification or promotion prompts.

Patch-worker order::

    proposal.patch present
      -> missing matching patch-review.json ? ``review_patch``
      -> missing matching patch-dry-run.json ? ``patch_dry_run``
      -> patch not applied (hash match) ? ``apply_patch``
      -> then verification
      -> then promotion preview/promote
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

# ---------------------------------------------------------------------------
# Public model
# ---------------------------------------------------------------------------

Gate = Literal[
    "inspect",
    "run_worker",
    "review_patch",
    "patch_dry_run",
    "apply_patch",
    "verify",
    "promotion_preview",
    "promote",
    "resolve_blocker",
    "inspect_failure",
    "cleanup_preview",
    "closed",
]

SAFETY_READ_ONLY = "read_only"
SAFETY_APPROVAL_REQUIRED = "approval_required"
SAFETY_DANGEROUS = "dangerous"


class TaskNextGate:
    """Canonical read-only gate resolver result.  Matches the plan schema."""

    __slots__ = (
        "task_id",
        "label",
        "gate",
        "command",
        "safety_class",
        "requires_human_approval",
        "supervisor_may_auto_run",
        "reason",
        "evidence_paths",
    )

    def __init__(
        self,
        task_id: str,
        label: str,
        gate: Gate,
        *,
        command: str | None = None,
        safety_class: str = SAFETY_READ_ONLY,
        requires_human_approval: bool = False,
        supervisor_may_auto_run: bool = True,
        reason: str = "",
        evidence_paths: list[str] | None = None,
    ) -> None:
        self.task_id = task_id
        self.label = label
        self.gate = gate
        self.command = command
        self.safety_class = safety_class
        self.requires_human_approval = requires_human_approval
        self.supervisor_may_auto_run = supervisor_may_auto_run
        self.reason = reason
        self.evidence_paths = evidence_paths or []

    @property
    def dashboard_label(self) -> str:
        return self.label

    @property
    def dashboard_command(self) -> str | None:
        return self.command


# ---------------------------------------------------------------------------
# QwopusEvidence (minimal dataclass so we don't import qwopus_evidence at
# module level in production code; actual runtime consumers still use the
# real module.)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _QwopusEvidence:
    agent_id: str
    task_path: Path
    proposal_patch_path: Path
    has_proposal_patch: bool


def _read_json_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _read_qwopus_evidence(root: Path, task_id: str, agent_id: str = "qwopus-implementer") -> _QwopusEvidence | None:
    path = _task_dir(root, task_id)
    agent_dir = path / "agents" / agent_id
    if not agent_dir.exists() or not agent_dir.is_dir():
        return None

    proposal_patch_path = agent_dir / "proposal.patch"
    has_patch = proposal_patch_path.exists() and proposal_patch_path.stat().st_size > 0

    known_artifacts = [
        proposal_patch_path,
        agent_dir / "result.md",
        agent_dir / "raw_output.md",
        agent_dir / "run.json",
        agent_dir / "worker_failed.json",
    ]
    if not any(p.exists() for p in known_artifacts):
        return None

    return _QwopusEvidence(
        agent_id=agent_id,
        task_path=path,
        proposal_patch_path=proposal_patch_path,
        has_proposal_patch=has_patch,
    )


def _patch_application_succeeded(root: Path, task_id: str, agent_id: str = "qwopus-implementer") -> bool:
    """Check if a Qwopus proposal patch was successfully applied (hash match)."""
    path = _task_dir(root, task_id)
    agent_dir = path / "agents" / agent_id
    proposal_patch_path = agent_dir / "proposal.patch"

    if not (proposal_patch_path.exists() and proposal_patch_path.stat().st_size > 0):
        return False

    patch_hash = hashlib.sha256(proposal_patch_path.read_bytes()).hexdigest()
    for evid in [path / "patch-application.json", path / "patches" / f"{patch_hash}.json"]:
        payload = _read_json_object(evid)
        if (
            payload.get("task_id") == task_id
            and payload.get("agent_id") == agent_id
            and payload.get("patch_hash") == patch_hash
            and isinstance(payload.get("applied_at"), str)
        ):
            return True
    return False


# ---------------------------------------------------------------------------
# Gate resolution helpers
# ---------------------------------------------------------------------------


def _next_patch_gate_command(task_path: Path, task_id: str, agent_id: str) -> tuple[str, str]:
    review_exists, dry_run_exists = _matching_patch_gate_evidence(task_path, agent_id)
    if not review_exists:
        return ("review-patch", f"devflow task review-patch {task_id} --agent {agent_id}")
    if not dry_run_exists:
        return ("patch-dry-run", f"devflow task patch-dry-run {task_id} --agent {agent_id}")
    return ("apply-patch", f"devflow task apply-patch {task_id} --agent {agent_id}")


def _matching_patch_gate_evidence(task_path: Path, agent_id: str) -> tuple[bool, bool]:
    proposal_patch_path = task_path / "agents" / agent_id / "proposal.patch"
    if not proposal_patch_path.exists():
        return False, False
    run_dir = task_path / "local-model-runs" / f"agent-{_slug(agent_id)}"
    run_patch = run_dir / "proposal.patch"
    if not run_patch.exists() or _hash_file(run_patch) != _hash_file(proposal_patch_path):
        return False, False
    return (run_dir / "patch-review.json").exists(), (run_dir / "patch-dry-run.json").exists()


def _slug(value: str) -> str:
    return "".join(c if c.isalnum() or c in "_.-" else "-" for c in value).strip("-") or "agent"


def _hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# Core resolver
# ---------------------------------------------------------------------------


def resolve_task_next_gate(root: Path, task_id: str) -> TaskNextGate:
    """Return the *highest-priority* next gate for *task_id*, respecting the
    Qwopus patch-gate ladder before verification/promotion."""

    task_path = _task_dir(root, task_id)
    if not task_path.exists():
        return _gate(
            "closed",
            "Closed task",
            task_id,
            approval_required=False,
            reason="Task does not exist.",
        )

    status = _read_task_status(task_path / "task.yaml")
    if status is None:
        status = "created"

    # Terminal states
    if status == "closed":
        return _gate("closed", "Closed task", task_id, approval_required=False, reason="Task is closed.")
    if status == "promoted":
        return _gate(
            "inspect", "Inspect promoted task", task_id,
            approval_required=False, reason="Task has been promoted.",
        )

    # --- inspection: failed verification -----------------------------------
    verification_path = task_path / "verification.json"
    verification = json.loads(verification_path.read_text()) if verification_path.exists() else None
    vs: str = (verification.get("status", "not_run") if isinstance(verification, dict) else "not_run")

    if vs == "failed":
        return _gate(
            "inspect_failure", "Inspect verification failure", task_id,
            command=_scope(f'devflow task log {task_id} --verify --tail 80'),
            reason="Verification failed and needs inspection.",
        )

    # --- Qwopus patch-gate ladder -----------------------------------------
    pr = _patch_readiness(root, task_id, status, vs)
    if pr["review_state"] in ("review_patch", "patch_dry_run", "apply_patch"):
        return TaskNextGate(
            task_id=task_id,
            label=_gate_label(pr["gate"]),
            gate=pr["gate"],
            command=pr.get("command"),
            safety_class=SAFETY_APPROVAL_REQUIRED,
            requires_human_approval=True,
            reason=f"Qwopus patch evidence: {_slice_reason(pr)}",
        )

    # --- normal pipeline --------------------------------------------------
    if status == "created":
        return _gate(
            "run_worker", "Run task", task_id,
            command=_scope(f'devflow task run {task_id} --worker shell -- "<command>"'),
            approval_required=True,
            reason="Task exists but no worker has run.",
        )

    # Complete or unverified -> verify (unless verified+promotion-ready)
    if vs == "passed" and status == "verified":
        return _gate(
            "promotion_preview", "Preview promotion", task_id,
            command=_scope(f'devflow task promote-preview {task_id}'),
            approval_required=True,
            reason="Verification passed; preview before promote.",
        )
    if vs in ("not_run", "pending") or status != "verified":
        if vs == "passed" and _promotion_ready(root, task_id):
            return _gate(
                "promotion_preview", "Preview promotion", task_id,
                command=_scope(f'devflow task promote-preview {task_id}'),
                approval_required=True,
                reason="Verification passed; preview before promote.",
            )
        return _gate(
            "verify", "Run verification", task_id,
            command=_scope(f'devflow task verify {task_id} --shell "<command>"'),
            approval_required=True,
            reason="Worker output available but verification has not passed.",
        )

    # Already verified + promotion ready -> promote-preview
    if vs == "passed" and _promotion_ready(root, task_id):
        return _gate(
            "promotion_preview", "Preview promotion", task_id,
            command=_scope(f'devflow task promote-preview {task_id}'),
            approval_required=True,
            reason="Fully verified; review promotion preview.",
        )

    # Fallback
    return _gate("inspect", "Inspect task", task_id, approval_required=False, reason="No safer automated action inferred.")


# ---------------------------------------------------------------------------
# Compat adapter (dashboard_next_action shape)
# ---------------------------------------------------------------------------


class DashboardActionAdapter:
    """Maps TaskNextGate -> {label, task_id, command, reason} for legacy consumers."""

    @staticmethod
    def from_gate(gate: TaskNextGate) -> dict:
        return {
            "label": gate.label,
            "task_id": gate.task_id,
            "command": gate.command,
            "reason": gate.reason,
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _task_dir(root: Path, task_id: str) -> Path:
    return root / ".devflow" / "tasks" / task_id


def _read_task_status(yaml_path: Path) -> str | None:
    if not yaml_path.exists():
        return None
    text = yaml_path.read_text(encoding="utf-8")
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        data = _read_yaml_scalars(text)
    except Exception:
        return None
    status = data.get("status") if isinstance(data, dict) else None
    return str(status) if isinstance(status, str) else None


def _read_yaml_scalars(text: str) -> dict[str, Any]:
    """Read the small task.yaml scalar subset used by DevFlow task records."""
    data: dict[str, Any] = {}
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        value = value.strip()
        if value == "null":
            parsed: Any = None
        elif value == "true":
            parsed = True
        elif value == "false":
            parsed = False
        elif value.startswith('"'):
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                parsed = value.strip('"')
        else:
            parsed = value
        data[key.strip()] = parsed
    return data


def _scope(cmd: str) -> str:
    """Stub for project-scope injection (mirrors existing _scope_task_command semantics)."""
    return cmd


def _promotion_ready(root: Path, task_id: str) -> bool:
    pp = _task_dir(root, task_id) / "promotion-ready.json"
    if not pp.exists():
        return False
    try:
        data = json.loads(pp.read_text(encoding="utf-8"))
    except Exception:
        return False
    ready = data.get("ready") if isinstance(data, dict) else None
    return bool(ready)


def _gate(
    gateway: Gate,
    label: str,
    task_id: str,
    *,
    command: str | None = None,
    approval_required: bool = False,
    reason: str = "",
) -> TaskNextGate:
    return TaskNextGate(
        task_id=task_id,
        label=label,
        gate=gateway,
        command=command,
        safety_class=SAFETY_APPROVAL_REQUIRED if approval_required else SAFETY_READ_ONLY,
        requires_human_approval=approval_required,
        reason=reason,
    )


def _gate_label(gate_str: str) -> str:
    return {
        "review_patch": "Review patch",
        "patch_dry_run": "Patch dry-run",
        "apply_patch": "Apply patch",
        "review-patch": "Review patch",
        "patch-dry-run": "Patch dry-run",
        "apply-patch": "Apply patch",
    }.get(gate_str, gate_str)


def _slice_reason(pr: dict[str, Any]) -> str:
    """Short reason string for log messages."""
    state = pr.get("review_state") or ""
    if state == "review_patch":
        return "patch needs review"
    if state == "patch_dry_run":
        return "patch dry-run needed"
    if state == "apply_patch":
        return "patch needs application"
    if state == "needs_verification":
        return "patch needs verification"
    return "unmatched patch stage"


# ---------------------------------------------------------------------------
# Patch-readiness (mirrors Qwopus ladder so consumers agree on order)
# ---------------------------------------------------------------------------


def _patch_readiness(
    root: Path,
    task_id: str,
    task_status: str,
    verification_status: str,
) -> dict[str, Any]:
    evid = _read_qwopus_evidence(root, task_id)

    # Verified + verification passed → promotion_preview regardless of any evidence files
    if task_status == "verified" and verification_status == "passed":
        return {"review_state": "not_ready", "gate": "promotion_preview"}

    # No proposal patch exists — use status-based defaults
    if evid is None or not evid.has_proposal_patch:
        if task_status in ("created", "running"):
            return {"review_state": "not_ready", "gate": "verify"}
        if _promotion_ready(root, task_id):
            return {"review_state": "not_ready", "gate": "promotion_preview"}
        return {"review_state": "needs_verification", "gate": "verify"}

    # Has proposal.patch — always walk the patch ladder regardless of task status
    if not _patch_application_succeeded(root, task_id):
        review_exists, dry_run_exists = _matching_patch_gate_evidence(evid.task_path, evid.agent_id)
        if not review_exists:
            return {
                "review_state": "review_patch",
                "gate": "review_patch",
                "command": f"devflow task review-patch {task_id} --agent {evid.agent_id}",
            }
        if not dry_run_exists:
            return {
                "review_state": "patch_dry_run",
                "gate": "patch_dry_run",
                "command": f"devflow task patch-dry-run {task_id} --agent {evid.agent_id}",
            }
        # All gates present but patch not applied → apply_patch
        return {
            "review_state": "apply_patch",
            "gate": "apply_patch",
            "command": f"devflow task apply-patch {task_id} --agent {evid.agent_id}",
        }

    # Patch already succeeded — matching review/dry-run evidence must still exist.
    has_review, has_dry_run = _matching_patch_gate_evidence(evid.task_path, evid.agent_id)
    if not has_review:
        return {
            "review_state": "review_patch",
            "gate": "review_patch",
            "command": f"devflow task review-patch {task_id} --agent {evid.agent_id}",
        }
    if not has_dry_run:
        return {
            "review_state": "patch_dry_run",
            "gate": "patch_dry_run",
            "command": f"devflow task patch-dry-run {task_id} --agent {evid.agent_id}",
        }

    if verification_status != "passed":
        return {"review_state": "needs_verification", "gate": "verify"}

    if _promotion_ready(root, task_id):
        return {"review_state": "not_ready", "gate": "promotion_preview"}

    return {"review_state": "needs_verification", "gate": "verify"}


# Export public API
__all__ = [
    "TaskNextGate",
    "resolve_task_next_gate",
    "DashboardActionAdapter",
]
