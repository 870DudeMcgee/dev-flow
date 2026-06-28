from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any


LOCAL_DEFAULT_PROVIDER_ID = "custom:qwen35-mtp"
LOCAL_DEFAULT_MODEL_ID = "qwen35-9b-mtp"

WEIGHT_ORDER = {"tiny": 0, "small": 1, "medium": 2, "heavy": 3}


@dataclass(frozen=True)
class MachineCapability:
    total_memory_gb: int | None
    machine_class: str
    max_recommended_weight_class: str
    local_model_concurrency: dict[str, Any]

    def to_payload(self) -> dict[str, Any]:
        return {
            "total_memory_gb": self.total_memory_gb,
            "machine_class": self.machine_class,
            "max_recommended_weight_class": self.max_recommended_weight_class,
            "local_model_concurrency": dict(self.local_model_concurrency),
        }


def discover_machine_capability() -> MachineCapability:
    memory_gb = _physical_memory_gb()
    return MachineCapability(
        total_memory_gb=memory_gb,
        machine_class=_machine_class(memory_gb),
        max_recommended_weight_class=_max_recommended_weight(memory_gb),
        local_model_concurrency=local_model_concurrency_policy(),
    )


def local_model_concurrency_policy() -> dict[str, Any]:
    return {
        "mode": "single_flight",
        "max_parallel_local_model_runs": 1,
        "reason": "Local model runtimes share RAM/VRAM pressure; DevFlow serializes them for safety.",
    }


def classify_model_fit(
    model: dict[str, Any],
    *,
    machine: MachineCapability | None = None,
    preferred: bool = False,
) -> dict[str, Any]:
    capability = machine or discover_machine_capability()
    weight = _model_weight_class(model)
    allowed = WEIGHT_ORDER[weight] <= WEIGHT_ORDER[capability.max_recommended_weight_class]
    if preferred and allowed:
        status = "preferred"
        reason = "Preferred local Hermes model for this machine."
    elif allowed:
        status = "allowed"
        reason = f"Model weight {weight} fits the current {capability.machine_class} policy."
    else:
        status = "not_recommended"
        memory = f"{capability.total_memory_gb} GB" if capability.total_memory_gb is not None else "unknown RAM"
        reason = (
            f"Model weight {weight} exceeds the {capability.max_recommended_weight_class} "
            f"recommendation for this machine ({memory})."
        )
    return {
        "status": status,
        "weight_class": weight,
        "machine_class": capability.machine_class,
        "max_recommended_weight_class": capability.max_recommended_weight_class,
        "reason": reason,
    }


def _physical_memory_gb() -> int | None:
    override = os.environ.get("DEVFLOW_MACHINE_RAM_GB")
    if override:
        try:
            return max(1, int(float(override)))
        except ValueError:
            return None
    try:
        pages = os.sysconf("SC_PHYS_PAGES")
        page_size = os.sysconf("SC_PAGE_SIZE")
    except (AttributeError, OSError, ValueError):
        return None
    try:
        return max(1, round((int(pages) * int(page_size)) / (1024**3)))
    except (TypeError, ValueError, OverflowError):
        return None


def _machine_class(memory_gb: int | None) -> str:
    if memory_gb is None:
        return "unknown"
    if memory_gb <= 18:
        return "mac_mini"
    if memory_gb >= 48:
        return "mac_studio"
    return "workstation"


def _max_recommended_weight(memory_gb: int | None) -> str:
    if memory_gb is None:
        return "small"
    if memory_gb < 10:
        return "small"
    if memory_gb <= 24:
        return "medium"
    return "heavy"


def _model_weight_class(model: dict[str, Any]) -> str:
    explicit = model.get("weight_class")
    if isinstance(explicit, str) and explicit in WEIGHT_ORDER:
        return explicit
    params = _numeric_params(model)
    if params is not None:
        if params >= 20_000_000_000:
            return "heavy"
        if params >= 7_000_000_000:
            return "medium"
        if params >= 2_000_000_000:
            return "small"
        return "tiny"
    model_id = str(model.get("id") or model.get("model") or model.get("name") or "").lower()
    if any(token in model_id for token in ("32b", "31b", "36b", "70b")):
        return "heavy"
    if any(token in model_id for token in ("14b", "12b", "9b", "7b")):
        return "medium"
    if any(token in model_id for token in ("3b", "1.5b", "1b")):
        return "small"
    return "small"


def _numeric_params(model: dict[str, Any]) -> int | None:
    for key in ("n_params", "parameter_count", "parameters"):
        value = model.get(key)
        if isinstance(value, bool) or value is None:
            continue
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        if isinstance(value, str):
            stripped = value.strip().lower().replace(",", "")
            try:
                if stripped.endswith("b"):
                    return int(float(stripped[:-1]) * 1_000_000_000)
                return int(float(stripped))
            except ValueError:
                continue
    return None
