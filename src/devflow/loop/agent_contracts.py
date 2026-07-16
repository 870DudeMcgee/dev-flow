"""Agent contract schema and enforcement (M2-S3).

Implements blueprint §7.1–7.2 typed agent contracts. Each role gains an optional
contract with allowed/forbidden actions, required inputs/outputs, evidence rules,
completion/failure conditions, handoff contract, and resource profile.

Contracts are **additive** — existing roles load unchanged with ``contract=None``.
Enforcement is a standalone function that can be called before dispatch or from
the authorization path.

The contract schema uses functional role names only — no model identity (per the
user's naming rule).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Resource profile (blueprint §7.1)
# ---------------------------------------------------------------------------

class ContextSize(str, Enum):
    """Expected context window requirement."""

    small = "small"
    medium = "medium"
    large = "large"


class ModelClass(str, Enum):
    """What kind of model/tool can serve this contract."""

    any = "any"
    local = "local"
    cloud = "cloud"
    frontier = "frontier"
    deterministic = "deterministic"


class RetryPolicy(str, Enum):
    """Retry behavior for this contract."""

    bounded = "bounded"
    none = "none"


class ResourceProfile(BaseModel):
    """Blueprint §7.1 resource profile — what the contract needs to run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    context_size: ContextSize = ContextSize.medium
    expected_duration_minutes: int = Field(default=5, ge=1, le=120)
    model_class: ModelClass = ModelClass.any
    memory_needs: str = "normal"  # normal/heavy
    retry_policy: RetryPolicy = RetryPolicy.bounded


# ---------------------------------------------------------------------------
# Agent contract (blueprint §7.1–7.2)
# ---------------------------------------------------------------------------

class AgentContract(BaseModel):
    """Typed, enforceable contract for one bounded worker responsibility.

    A prompt may describe expertise and behavior, but the contract is the
    enforceable interface around that prompt (blueprint §7.1).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    purpose: str = Field(min_length=1)
    allowed_actions: tuple[str, ...] = ()
    forbidden_actions: tuple[str, ...] = ()
    required_inputs: tuple[str, ...] = ()
    required_outputs: tuple[str, ...] = ()
    evidence_rules: tuple[str, ...] = ()
    completion_conditions: tuple[str, ...] = ()
    failure_conditions: tuple[str, ...] = ()
    handoff_contract: str | None = None
    resource: ResourceProfile = Field(default_factory=ResourceProfile)


# ---------------------------------------------------------------------------
# Contract check result
# ---------------------------------------------------------------------------

class ContractCheckResult(BaseModel):
    """Result of checking requested actions against a contract.

    ``passed`` is True only when no forbidden action is requested and all
    required inputs are present. ``evidence_rules`` are advisory metadata
    (not a hard block in M2 — enforcement hardens in M4).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    passed: bool
    violations: tuple[str, ...] = ()
    advisory_evidence_rules: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# Enforcement
# ---------------------------------------------------------------------------

def check_contract(
    contract: AgentContract,
    *,
    requested_actions: tuple[str, ...] = (),
    available_inputs: tuple[str, ...] = (),
) -> ContractCheckResult:
    """Check requested actions and inputs against a contract.

    Returns a :class:`ContractCheckResult`. Hard blocks:

    - Any requested action matching a ``forbidden_action``
    - Any ``required_input`` not in ``available_inputs``

    Advisory (not blocking in M2):

    - ``evidence_rules`` are attached as metadata for downstream consumers

    Parameters
    ----------
    contract
        The agent contract to check against.
    requested_actions
        Actions the node wants to perform (e.g. ``("read", "write:workspace")``).
    available_inputs
        Artifact keys present in the run directory (e.g. ``("spec", "plan")``).
    """
    violations: list[str] = []

    # Hard block: forbidden actions
    for action in requested_actions:
        for forbidden in contract.forbidden_actions:
            if _action_matches(action, forbidden):
                violations.append(
                    f"forbidden action {action!r} matches {forbidden!r}"
                )

    # Hard block: missing required inputs
    available_set = set(available_inputs)
    for required in contract.required_inputs:
        if required not in available_set:
            violations.append(
                f"required input {required!r} is not available"
            )

    return ContractCheckResult(
        passed=len(violations) == 0,
        violations=tuple(violations),
        advisory_evidence_rules=contract.evidence_rules,
    )


def _action_matches(requested: str, forbidden: str) -> bool:
    """Check if a requested action matches a forbidden pattern.

    Supports prefix matching with ``:`` separator. ``"write:main_branch"``
    matches ``"write"`` (prefix) but ``"write"`` does not match
    ``"write:main_branch"`` (more specific).
    """
    if requested == forbidden:
        return True
    # A forbidden prefix like "write" matches "write:anything"
    if ":" in requested and forbidden == requested.split(":")[0]:
        return True
    return False


# ---------------------------------------------------------------------------
# Default contracts for existing roles (optional — roles still work without)
# ---------------------------------------------------------------------------

_DEFAULT_CONTRACTS: dict[str, AgentContract] = {}


def get_default_contract(role_name: str) -> AgentContract | None:
    """Return a populated default contract for a role, or None.

    Currently returns None for all roles — contracts are populated when
    roles are explicitly upgraded. This keeps existing roles backward
    compatible (contract=None).
    """
    return _DEFAULT_CONTRACTS.get(role_name)


__all__ = [
    "AgentContract",
    "ContractCheckResult",
    "ContextSize",
    "ModelClass",
    "ResourceProfile",
    "RetryPolicy",
    "check_contract",
    "get_default_contract",
]
