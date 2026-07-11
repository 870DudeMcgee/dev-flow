"""Tests for the capability-driven model routing architecture.

Tests the three-layer separation:
  registry.py   — model entries (what exists)
  roles.py      — role definitions (what's required)
  routing.py    — role → model resolution (how they connect)

Also verifies backward compatibility with the old model_router.py API
so existing callers (execution.py, server.py) work unchanged.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from devflow.loop.registry import (
    ModelEntry,
    ModelRegistry,
    get_registry,
    load_registry_from_yaml,
)
from devflow.loop.roles import get_role, known_roles, role_requires
from devflow.loop.routing import (
    ResolvedSlot,
    resolve_role,
    resolve_role_compatible,
    set_active_profile,
    get_active_profile_name,
    list_profiles,
)
from devflow.loop.model_router import (
    resolve_role_slot,
    KNOWN_ROLES,
    ModelSlot,
)


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def restore_active_profile():
    """Prevent one profile-routing test from leaking global state into another."""
    original = get_active_profile_name()
    try:
        yield
    finally:
        set_active_profile(original)


SAMPLE_YAML = """\
models:
  model-a:
    display_name: "Model A"
    provider: local
    transport: openai-http
    endpoint: "http://localhost:9000"
    cost_class: local
    capabilities:
      - code_generation
      - structured_output
  model-b:
    display_name: "Model B"
    provider: zai
    transport: hermes-chat
    endpoint: "hermes://chat/zai/model-b"
    cost_class: included_subscription
    capabilities:
      - high_level_reasoning
      - code_generation
      - structured_output
    available: false
"""


@pytest.fixture
def tmp_yaml(tmp_path: Path) -> Path:
    p = tmp_path / "models.yaml"
    p.write_text(SAMPLE_YAML)
    return p


@pytest.fixture
def small_registry() -> ModelRegistry:
    return ModelRegistry({
        "cheap-builder": ModelEntry(
            name="cheap-builder",
            display_name="Cheap Builder",
            provider="local",
            transport="openai-http",
            endpoint="http://localhost:8001",
            capabilities=("code_generation", "structured_output", "edit_planning"),
            cost_class="local",
        ),
        "smart-judge": ModelEntry(
            name="smart-judge",
            display_name="Smart Judge",
            provider="zai",
            transport="hermes-chat",
            endpoint="hermes://chat/zai/smart-judge",
            capabilities=("high_level_reasoning", "evidence_synthesis", "decision_making"),
            cost_class="included_subscription",
        ),
        "retired-model": ModelEntry(
            name="retired-model",
            display_name="Retired",
            provider="local",
            transport="openai-http",
            endpoint="http://localhost:8002",
            capabilities=("code_generation",),
            cost_class="local",
            retired=True,
        ),
        "unavailable-model": ModelEntry(
            name="unavailable-model",
            display_name="Unavailable",
            provider="local",
            transport="openai-http",
            endpoint="http://localhost:8003",
            capabilities=("code_generation",),
            cost_class="local",
            available=False,
        ),
    })


# ---------------------------------------------------------------------------
# Registry tests
# ---------------------------------------------------------------------------
class TestModelEntry:
    def test_valid_entry(self):
        e = ModelEntry(
            name="test",
            display_name="Test",
            provider="local",
            transport="openai-http",
            endpoint="http://localhost:9000",
            capabilities=("code_generation",),
            cost_class="local",
        )
        assert e.is_eligible
        assert e.has_capability("code_generation")

    def test_invalid_cost_class(self):
        with pytest.raises(ValueError, match="invalid cost_class"):
            ModelEntry(
                name="test",
                display_name="Test",
                provider="local",
                transport="openai-http",
                endpoint="http://localhost:9000",
                capabilities=("code_generation",),
                cost_class="bogus",
            )

    def test_retired_not_eligible(self):
        e = ModelEntry(
            name="test",
            display_name="Test",
            provider="local",
            transport="openai-http",
            endpoint="",
            capabilities=(),
            cost_class="local",
            retired=True,
        )
        assert not e.is_eligible

    def test_has_all_capabilities(self):
        e = ModelEntry(
            name="t", display_name="T", provider="local", transport="openai-http",
            endpoint="", capabilities=("a", "b", "c"), cost_class="local",
        )
        assert e.has_all_capabilities(("a", "b"))
        assert not e.has_all_capabilities(("a", "z"))


class TestModelRegistry:
    def test_query_eligible(self, small_registry: ModelRegistry):
        eligible = small_registry.eligible()
        names = [e.name for e in eligible]
        assert "cheap-builder" in names
        assert "smart-judge" in names
        assert "retired-model" not in names
        assert "unavailable-model" not in names

    def test_query_by_capability(self, small_registry: ModelRegistry):
        builders = small_registry.with_capability("code_generation")
        assert len(builders) == 1  # only cheap-builder (retired/unavailable excluded)
        assert builders[0].name == "cheap-builder"

    def test_query_by_capabilities_multiple(self, small_registry: ModelRegistry):
        result = small_registry.with_capabilities(("code_generation", "structured_output"))
        assert len(result) == 1
        assert result[0].name == "cheap-builder"

    def test_cost_class_filter(self, small_registry: ModelRegistry):
        local_models = small_registry.by_cost_class("local")
        assert len(local_models) == 1
        assert local_models[0].name == "cheap-builder"


class TestRegistryYAML:
    def test_load_from_yaml(self, tmp_yaml: Path):
        reg = load_registry_from_yaml(tmp_yaml)
        assert len(reg) == 2
        assert "model-a" in reg
        assert "model-b" in reg

    def test_entry_fields(self, tmp_yaml: Path):
        reg = load_registry_from_yaml(tmp_yaml)
        a = reg.get("model-a")
        assert a is not None
        assert a.provider == "local"
        assert a.cost_class == "local"
        assert a.transport == "openai-http"
        assert "code_generation" in a.capabilities

    def test_load_missing_file(self, tmp_path: Path):
        reg = load_registry_from_yaml(tmp_path / "nonexistent.yaml")
        assert len(reg) == 0

    def test_production_models_yaml_loads(self):
        """The real models.yaml must load without errors."""
        import devflow.loop.registry as reg_mod
        yaml_path = Path(reg_mod.__file__).parent / "models.yaml"
        reg = load_registry_from_yaml(yaml_path)
        assert len(reg) >= 4  # at least the current fleet
        # Every model must have at least one capability
        for entry in reg.all():
            assert len(entry.capabilities) > 0, f"{entry.name} has no capabilities"


# ---------------------------------------------------------------------------
# Role definition tests
# ---------------------------------------------------------------------------
class TestRoles:
    def test_seven_canonical_roles(self):
        assert set(known_roles()) == {
            "brainstorm", "planner", "planning_judge",
            "builder", "build_judge", "verifier", "final_judge",
        }

    def test_every_role_has_required_capabilities(self):
        for name in known_roles():
            caps = role_requires(name)
            assert len(caps) > 0, f"Role '{name}' has no required capabilities"

    def test_get_unknown_role(self):
        assert get_role("nonexistent") is None

    def test_role_requires_unknown(self):
        with pytest.raises(ValueError, match="Unknown DevFlow role"):
            role_requires("bogus")

    def test_roles_have_cost_prefs(self):
        for name in known_roles():
            role = get_role(name)
            assert len(role.preferred_cost_classes) > 0


# ---------------------------------------------------------------------------
# Routing tests
# ---------------------------------------------------------------------------
class TestRouting:
    def test_resolve_builder_to_cheap_local(self, small_registry: ModelRegistry):
        slot = resolve_role("builder", registry=small_registry, profile_name="custom")
        assert slot.model_name == "cheap-builder"
        assert slot.provider == "local"
        assert slot.endpoint == "http://localhost:8001"

    def test_resolve_final_judge_to_subscription(self, small_registry: ModelRegistry):
        slot = resolve_role("final_judge", registry=small_registry, profile_name="custom")
        assert slot.model_name == "smart-judge"
        assert slot.cost_class == "included_subscription"

    def test_override_takes_precedence(self, small_registry: ModelRegistry):
        slot = resolve_role(
            "builder",
            override_model="cheap-builder",
            registry=small_registry,
            profile_name="custom",
        )
        assert slot.model_name == "cheap-builder"
        assert slot.resolved_via == "override"

    def test_override_must_satisfy_capabilities(self, small_registry: ModelRegistry):
        # smart-judge doesn't have edit_planning, so it can't be builder
        # even with an override.
        slot = resolve_role(
            "builder",
            override_model="smart-judge",
            registry=small_registry,
            profile_name="custom",
        )
        # Falls through to auto routing, which picks cheap-builder
        assert slot.model_name == "cheap-builder"
        assert slot.resolved_via != "override"

    def test_unknown_role_raises(self, small_registry: ModelRegistry):
        with pytest.raises(ValueError, match="Unknown DevFlow role"):
            resolve_role("nonexistent", registry=small_registry)

    def test_no_eligible_model_raises(self):
        empty_reg = ModelRegistry()
        with pytest.raises(ValueError, match="No eligible model"):
            resolve_role("builder", registry=empty_reg, profile_name="custom")

    def test_retired_model_not_selected(self, small_registry: ModelRegistry):
        # retired-model has code_generation but is retired
        slot = resolve_role("builder", registry=small_registry, profile_name="custom")
        assert slot.model_name != "retired-model"

    def test_unavailable_model_not_selected(self, small_registry: ModelRegistry):
        slot = resolve_role("builder", registry=small_registry, profile_name="custom")
        assert slot.model_name != "unavailable-model"

    def test_resolved_slot_attributes(self, small_registry: ModelRegistry):
        slot = resolve_role("builder", registry=small_registry, profile_name="custom")
        assert hasattr(slot, "role")
        assert hasattr(slot, "model_name")
        assert hasattr(slot, "provider")
        assert hasattr(slot, "endpoint")
        assert hasattr(slot, "transport")
        assert hasattr(slot, "cost_class")
        assert hasattr(slot, "resolved_via")
        # Backward compat: .model alias
        assert slot.model == slot.model_name


# ---------------------------------------------------------------------------
# Backward compatibility tests
# ---------------------------------------------------------------------------
class TestBackwardCompat:
    def test_old_role_names_resolve(self):
        """Legacy role names from the old ROLE_SLOTS table still work."""
        for old_name in ("builder", "judge", "planner", "planning_judge"):
            slot = resolve_role_slot(old_name)
            assert isinstance(slot, ModelSlot)
            assert slot.model  # has a non-empty model name
            assert slot.endpoint  # has a non-empty endpoint

    def test_judge_alias_maps_to_build_judge(self):
        slot = resolve_role_slot("judge")
        assert slot.role == "build_judge"

    def test_model_specific_verifier_alias_is_not_a_role(self):
        with pytest.raises(ValueError, match="Unknown DevFlow role"):
            resolve_role_slot("glm_verifier")

    def test_known_roles_matches_canonical(self):
        assert set(KNOWN_ROLES) == set(known_roles())

    def test_model_slot_is_resolved_slot(self):
        assert ModelSlot is ResolvedSlot

    def test_resolve_role_compatible_works(self):
        slot = resolve_role_compatible("builder")
        assert slot.role == "builder"

    def test_resolve_role_compatible_accepts_legacy(self):
        slot = resolve_role_compatible("judge")
        assert slot.role == "build_judge"


# ---------------------------------------------------------------------------
# Profile tests
# ---------------------------------------------------------------------------
class TestProfiles:
    def test_list_profiles_includes_defaults(self):
        profiles = list_profiles()
        assert "legacy-current" in profiles
        assert "studio-local-heavy" in profiles
        assert "mini-free-cloud" in profiles
        assert "custom" in profiles

    def test_profile_switch_changes_routing(self):
        set_active_profile("studio-local-heavy")
        assert get_active_profile_name() == "studio-local-heavy"
        slot = resolve_role("verifier")
        # studio-local-heavy prefers qwen-27b, but it's unavailable on the
        # Mini (available: false), so routing falls through to auto.
        assert slot.model_name != "qwen-27b-q5km"
        assert slot.resolved_via == "auto"
        set_active_profile("legacy-current")

    def test_profile_routes_to_available_free_model(self):
        """When the profile's preferred model IS available, routing uses it."""
        set_active_profile("mini-free-cloud")
        slot = resolve_role("builder")
        assert slot.model_name == "hy3-free"
        assert slot.resolved_via == "profile"
        set_active_profile("legacy-current")

    def test_mini_free_cloud_profile_routes_every_role_to_hy3_free(self):
        """Mac-mini free-cloud profile never wakes a local model."""
        set_active_profile("mini-free-cloud")
        for role_name in known_roles():
            slot = resolve_role(role_name)
            assert slot.model_name == "hy3-free"
            assert slot.cost_class == "free_cloud"
            assert slot.resolved_via == "profile"
        set_active_profile("legacy-current")

    def test_mini_ollama_profile_routes_all_roles_and_pins_qwen_model_id(self):
        """Mac-mini local profile uses Qwen for building and subscriptions for reasoning."""
        expected_models = {
            "brainstorm": "gpt-5.6-terra",
            "planner": "gpt-5.6-terra",
            "planning_judge": "gpt-5.6-luna",
            "builder": "qwen2.5-coder-7b-mini",
            "build_judge": "gpt-5.6-luna",
            "verifier": "gpt-5.6-luna",
            "final_judge": "gpt-5.6-terra",
        }
        assert set(expected_models) == set(known_roles())
        set_active_profile("mini-ollama")
        for role_name, expected_model in expected_models.items():
            slot = resolve_role(role_name)
            assert slot.model_name == expected_model
            assert slot.resolved_via == "profile"

        builder = resolve_role("builder")
        assert builder.endpoint == "http://127.0.0.1:8088"
        assert builder.model_id == "qwen2.5-coder-7b-mini"
        assert builder.cost_class == "local"

    def test_hy3_free_entry_uses_openrouter_free_slug(self):
        """The free-cloud route must never silently select a metered HY3 SKU."""
        entry = get_registry().get("hy3-free")
        assert entry is not None
        assert entry.cost_class == "free_cloud"
        assert entry.model_id.endswith(":free")

    def test_laguna_free_entry_uses_canonical_openrouter_slug(self):
        entry = get_registry().get("laguna-m1-free")

        assert entry is not None
        assert entry.provider == "openrouter"
        assert entry.cost_class == "free_cloud"
        assert entry.context_window == 262144
        assert entry.tool_support is True
        assert entry.model_id == "poolside/laguna-m.1:free"

    def test_laguna_builder_audition_profile_changes_only_builder(self):
        builder = resolve_role("builder", profile_name="mini-laguna-builder")
        brainstorm = resolve_role("brainstorm", profile_name="mini-laguna-builder")
        build_judge = resolve_role("build_judge", profile_name="mini-laguna-builder")

        assert builder.model_name == "laguna-m1-free"
        assert builder.resolved_via == "profile"
        assert brainstorm.model_name == "glm-5.2"
        assert build_judge.model_name == "ornith-9b-mini"

    def test_laguna_is_not_eligible_for_brainstorm(self):
        entry = get_registry().get("laguna-m1-free")

        assert entry is not None
        assert "structured_output" in entry.capabilities
        assert "high_level_reasoning" not in entry.capabilities
        assert "ambiguity_resolution" not in entry.capabilities

    def test_profile_falls_through_when_model_unavailable(self):
        """When a profile's preferred model is unavailable, routing falls
        through to automatic selection rather than failing."""
        # Build a registry where hy3-free is explicitly unavailable
        reg = get_registry()
        hy3_entry = reg.get("hy3-free")
        assert hy3_entry is not None
        unavailable_hy3 = ModelEntry(
            name="hy3-free",
            display_name="HY3 (unavailable test)",
            provider="openrouter",
            transport="openai-http",
            endpoint="https://openrouter.ai/api/v1",
            capabilities=hy3_entry.capabilities,
            cost_class="free_cloud",
            available=False,
        )
        test_entries = {name: e for name, e in zip(reg.names(), reg.all())}
        test_entries["hy3-free"] = unavailable_hy3
        test_reg = ModelRegistry(test_entries)
        set_active_profile("mini-free-cloud")
        slot = resolve_role("builder", registry=test_reg)
        assert slot.resolved_via == "auto"
        assert slot.model_name != "hy3-free"
        set_active_profile("legacy-current")


# ---------------------------------------------------------------------------
# Capability contract invariant tests
# ---------------------------------------------------------------------------
class TestCapabilityContracts:
    def test_every_profile_model_satisfies_role_requirements(self):
        """All models assigned by all profiles must satisfy the role's
        required capabilities. If a profile assigns a model that lacks
        required capabilities, routing will silently fall through to auto,
        which is a configuration error."""
        from devflow.loop.routing import _load_profiles_yaml, _reload_all
        _reload_all()
        profiles_data = _load_profiles_yaml()
        for profile_name, profile_data in profiles_data.get("profiles", {}).items():
            role_map = profile_data.get("roles", {})
            for role_name, model_name in role_map.items():
                role = get_role(role_name)
                if role is None:
                    continue
                # Check that the model exists and satisfies requirements
                from devflow.loop.registry import get_registry
                entry = get_registry().get(model_name)
                if entry is None:
                    pytest.fail(
                        f"Profile '{profile_name}' assigns unknown model "
                        f"'{model_name}' to role '{role_name}'"
                    )
                if not entry.has_all_capabilities(role.required_capabilities):
                    missing = set(role.required_capabilities) - set(entry.capabilities)
                    pytest.fail(
                        f"Profile '{profile_name}' assigns '{model_name}' to "
                        f"'{role_name}' but it lacks capabilities: {missing}"
                    )
