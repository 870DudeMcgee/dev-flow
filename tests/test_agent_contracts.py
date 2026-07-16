"""Tests for agent contract schema and enforcement (M2-S3)."""

from __future__ import annotations

import pytest

from devflow.loop.agent_contracts import (
    AgentContract,
    ContractCheckResult,
    ContextSize,
    ModelClass,
    ResourceProfile,
    RetryPolicy,
    check_contract,
    get_default_contract,
)
from devflow.loop.roles import ROLES, RoleDefinition, get_role, known_roles


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_contract(
    allowed_actions: tuple[str, ...] = ("read", "write:workspace"),
    forbidden_actions: tuple[str, ...] = ("write:main_branch", "network"),
    required_inputs: tuple[str, ...] = ("spec", "plan"),
    required_outputs: tuple[str, ...] = ("build-judge-report",),
    evidence_rules: tuple[str, ...] = ("cite_file_paths",),
    completion_conditions: tuple[str, ...] = ("diff_produced",),
    failure_conditions: tuple[str, ...] = ("timeout",),
) -> AgentContract:
    return AgentContract(
        purpose="Build one bounded slice",
        allowed_actions=allowed_actions,
        forbidden_actions=forbidden_actions,
        required_inputs=required_inputs,
        required_outputs=required_outputs,
        evidence_rules=evidence_rules,
        completion_conditions=completion_conditions,
        failure_conditions=failure_conditions,
    )


# ---------------------------------------------------------------------------
# Contract schema tests
# ---------------------------------------------------------------------------

def test_contract_frozen() -> None:
    """AgentContract is immutable."""
    contract = _make_contract()
    with pytest.raises(Exception):
        contract.purpose = "modified"  # type: ignore[misc]


def test_resource_profile_defaults() -> None:
    """ResourceProfile has correct defaults."""
    rp = ResourceProfile()
    assert rp.context_size == ContextSize.medium
    assert rp.expected_duration_minutes == 5
    assert rp.model_class == ModelClass.any
    assert rp.memory_needs == "normal"
    assert rp.retry_policy == RetryPolicy.bounded


def test_resource_profile_frozen() -> None:
    rp = ResourceProfile()
    with pytest.raises(Exception):
        rp.memory_needs = "heavy"  # type: ignore[misc]


def test_contract_serializes_json() -> None:
    """Contract round-trips through JSON."""
    contract = _make_contract()
    import json
    data = json.loads(contract.model_dump_json())
    restored = AgentContract.model_validate(data)
    assert restored == contract


def test_contract_minimal_valid() -> None:
    """Contract with only purpose is valid."""
    c = AgentContract(purpose="Do something")
    assert c.allowed_actions == ()
    assert c.forbidden_actions == ()
    assert c.resource.model_class == ModelClass.any


def test_contract_empty_purpose_rejected() -> None:
    """Purpose is required."""
    with pytest.raises(Exception):
        AgentContract(purpose="")


def test_context_size_enum() -> None:
    assert ContextSize.small.value == "small"
    assert ContextSize.medium.value == "medium"
    assert ContextSize.large.value == "large"


def test_model_class_enum() -> None:
    assert ModelClass.any.value == "any"
    assert ModelClass.local.value == "local"
    assert ModelClass.frontier.value == "frontier"
    assert ModelClass.deterministic.value == "deterministic"


# ---------------------------------------------------------------------------
# Enforcement tests
# ---------------------------------------------------------------------------

def test_forbidden_action_blocked() -> None:
    """Authorization rejects forbidden action."""
    contract = _make_contract()
    result = check_contract(
        contract,
        requested_actions=("read", "write:main_branch"),
        available_inputs=("spec", "plan"),
    )
    assert result.passed is False
    assert any("forbidden" in v for v in result.violations)


def test_allowed_action_passes() -> None:
    """Authorization allows explicitly allowed action."""
    contract = _make_contract()
    result = check_contract(
        contract,
        requested_actions=("read", "write:workspace"),
        available_inputs=("spec", "plan"),
    )
    assert result.passed is True
    assert result.violations == ()


def test_missing_required_input_blocked() -> None:
    """required_inputs absent → reject."""
    contract = _make_contract()
    result = check_contract(
        contract,
        requested_actions=("read",),
        available_inputs=("spec",),  # missing "plan"
    )
    assert result.passed is False
    assert any("required input" in v for v in result.violations)


def test_required_input_present_passes() -> None:
    """required_inputs present → allow."""
    contract = _make_contract()
    result = check_contract(
        contract,
        requested_actions=("read",),
        available_inputs=("spec", "plan"),
    )
    assert result.passed is True


def test_network_forbidden_blocked() -> None:
    """Network access forbidden → blocked when requested."""
    contract = _make_contract()
    result = check_contract(
        contract,
        requested_actions=("network",),
        available_inputs=("spec", "plan"),
    )
    assert result.passed is False
    assert any("network" in v for v in result.violations)


def test_action_prefix_matching() -> None:
    """A forbidden prefix matches more specific requests."""
    contract = AgentContract(
        purpose="test",
        forbidden_actions=("write",),
    )
    # "write:main_branch" should match forbidden "write"
    result = check_contract(contract, requested_actions=("write:main_branch",))
    assert result.passed is False


def test_evidence_rules_advisory() -> None:
    """evidence_rules attached as advisory metadata, not a hard block."""
    contract = _make_contract()
    result = check_contract(
        contract,
        requested_actions=("read",),
        available_inputs=("spec", "plan"),
    )
    assert result.passed is True
    assert "cite_file_paths" in result.advisory_evidence_rules


def test_handoff_contract_stored() -> None:
    """handoff_contract is accessible."""
    contract = AgentContract(
        purpose="test",
        handoff_contract="builder→judge: diff + evidence",
    )
    assert contract.handoff_contract == "builder→judge: diff + evidence"


def test_check_result_frozen() -> None:
    """ContractCheckResult is immutable."""
    result = ContractCheckResult(passed=True)
    with pytest.raises(Exception):
        result.passed = False  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Role backward compatibility tests
# ---------------------------------------------------------------------------

def test_legacy_roles_backward_compatible() -> None:
    """All 7 existing roles load without a contract."""
    roles = known_roles()
    assert len(roles) == 7
    for role_name in roles:
        role = get_role(role_name)
        assert role is not None
        assert role.contract is None  # no contract = backward compatible


def test_role_with_contract_loads() -> None:
    """A new role with a full contract loads correctly."""
    contract = _make_contract()
    role = RoleDefinition(
        name="contracted_builder",
        description="A builder with a typed contract",
        required_capabilities=("code_generation",),
        preferred_cost_classes=("free_cloud",),
        contract=contract,
    )
    assert role.contract is not None
    assert role.contract.purpose == "Build one bounded slice"


def test_role_contract_is_frozen() -> None:
    """RoleDefinition is frozen, including the contract field."""
    contract = _make_contract()
    role = RoleDefinition(
        name="test_role",
        description="test",
        required_capabilities=("a",),
        preferred_cost_classes=("b",),
        contract=contract,
    )
    with pytest.raises(Exception):
        role.contract = None  # type: ignore[misc]


def test_get_default_contract_returns_none() -> None:
    """Default contracts are not populated yet (roles upgrade individually)."""
    for role_name in known_roles():
        assert get_default_contract(role_name) is None


def test_roles_registry_unchanged() -> None:
    """The roles registry is not modified by M2-S3."""
    assert set(ROLES.keys()) == {
        "brainstorm", "planner", "planning_judge",
        "builder", "build_judge", "verifier", "final_judge",
    }
