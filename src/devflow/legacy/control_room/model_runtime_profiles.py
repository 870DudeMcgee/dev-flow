from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


RUNTIME_PROFILES_DIR = ".devflow/runtime-profiles"


@dataclass
class ModelRuntimeProfile:
    model_id: str
    total_runs: int = 0
    successes: int = 0
    failures: int = 0
    escalations_needed: int = 0
    verification_first_pass: int = 0
    boundary_violations: int = 0

    # Context ceiling tracking
    highest_successful_context: int = 0
    lowest_failed_context: int | None = None
    adjustment_count: int = 0
    current_reliable_context_tokens: int | None = None

    # Speed tracking
    total_latency_seconds: int = 0
    runs_with_latency: int = 0

    # Role-specific quality
    role_scores: dict[str, float] = field(default_factory=dict)
    total_runs_by_role: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "total_runs": self.total_runs,
            "successes": self.successes,
            "failures": self.failures,
            "escalations_needed": self.escalations_needed,
            "verification_first_pass": self.verification_first_pass,
            "boundary_violations": self.boundary_violations,
            "highest_successful_context": self.highest_successful_context,
            "lowest_failed_context": self.lowest_failed_context,
            "adjustment_count": self.adjustment_count,
            "current_reliable_context_tokens": self.current_reliable_context_tokens,
            "total_latency_seconds": self.total_latency_seconds,
            "runs_with_latency": self.runs_with_latency,
            "role_scores": dict(self.role_scores),
            "total_runs_by_role": dict(self.total_runs_by_role),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ModelRuntimeProfile:
        return cls(
            model_id=data["model_id"],
            total_runs=data.get("total_runs", 0),
            successes=data.get("successes", 0),
            failures=data.get("failures", 0),
            escalations_needed=data.get("escalations_needed", 0),
            verification_first_pass=data.get("verification_first_pass", 0),
            boundary_violations=data.get("boundary_violations", 0),
            highest_successful_context=data.get("highest_successful_context", 0),
            lowest_failed_context=data.get("lowest_failed_context"),
            adjustment_count=data.get("adjustment_count", 0),
            current_reliable_context_tokens=data.get("current_reliable_context_tokens"),
            total_latency_seconds=data.get("total_latency_seconds", 0),
            runs_with_latency=data.get("runs_with_latency", 0),
            role_scores=data.get("role_scores", {}),
            total_runs_by_role=data.get("total_runs_by_role", {}),
        )


def profile_path(root: Path, model_id: str) -> Path:
    safe_name = model_id.replace(":", "-").replace("/", "-")
    return root / RUNTIME_PROFILES_DIR / f"{safe_name}.json"


def load_profile(root: Path, model_id: str) -> ModelRuntimeProfile:
    path = profile_path(root, model_id)
    if not path.exists():
        return ModelRuntimeProfile(model_id=model_id)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return ModelRuntimeProfile.from_dict(data)
    except (json.JSONDecodeError, KeyError, TypeError):
        return ModelRuntimeProfile(model_id=model_id)


def save_profile(root: Path, profile: ModelRuntimeProfile) -> None:
    path = profile_path(root, profile.model_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(profile.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def suggest_reliable_context_adjustment(
    profile: ModelRuntimeProfile,
    advertised_context: int,
) -> int | None:
    """Suggest a new reliable context value based on runtime data.

    Returns None if no adjustment is needed, or a new token value if
    evidence suggests the current ceiling should change.
    """
    if profile.total_runs < 3:
        return None  # not enough data

    # If highest successful context is well below advertised, adjust down
    if profile.highest_successful_context > 0:
        safe_ceiling = int(profile.highest_successful_context * 1.1)  # 10% headroom
        if profile.current_reliable_context_tokens and safe_ceiling < profile.current_reliable_context_tokens:
            return max(safe_ceiling, 32768)
        if profile.current_reliable_context_tokens is None and safe_ceiling < int(advertised_context * 0.9):
            return safe_ceiling

    # If lowest_failed_context is below current, adjust down
    if (profile.lowest_failed_context
            and profile.current_reliable_context_tokens
            and profile.lowest_failed_context < profile.current_reliable_context_tokens):
        return max(profile.lowest_failed_context - 4096, 32768)

    return None


def update_from_scorecard(
    root: Path,
    scorecard: dict[str, Any],
    model_id: str,
    *,
    context_estimate: int = 0,
    role: str = "implementation_worker",
    latency_seconds: int = 0,
) -> ModelRuntimeProfile:
    """Update a model's runtime profile from a scorecard result. Returns the updated profile."""
    profile = load_profile(root, model_id)
    sc = scorecard.get("scorecard", {})

    profile.total_runs += 1

    # Success/failure
    status = sc.get("overall_rating", 0)
    if isinstance(status, (int, float)) and status >= 0.7:
        profile.successes += 1
        if context_estimate > profile.highest_successful_context:
            profile.highest_successful_context = context_estimate
    elif isinstance(status, (int, float)) and status < 0.5:
        profile.failures += 1
        if profile.lowest_failed_context is None or context_estimate < profile.lowest_failed_context:
            profile.lowest_failed_context = context_estimate

    # Verification first pass
    first_pass = sc.get("first_run_pass")
    if first_pass is True:
        profile.verification_first_pass += 1
    elif first_pass is False:
        pass  # didn't pass first time, recorded as is

    # Escalation
    if sc.get("frontier_escalation_needed") is True:
        profile.escalations_needed += 1

    # Boundary violations
    if sc.get("boundary_violations") is True:
        profile.boundary_violations += 1

    # Latency
    if latency_seconds > 0:
        profile.total_latency_seconds += latency_seconds
        profile.runs_with_latency += 1

    # Role tracking
    profile.total_runs_by_role[role] = profile.total_runs_by_role.get(role, 0) + 1

    save_profile(root, profile)
    return profile
