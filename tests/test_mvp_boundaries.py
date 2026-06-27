import pathlib
import unittest


class TestMVPBoundaries(unittest.TestCase):
    def test_cli_does_not_call_model_provider_modules(self):
        cli_source = pathlib.Path("src/devflow/cli.py").read_text(encoding="utf-8")

        forbidden_fragments = [
            "call_gemini",
            "call_ollama",
            "devflow.orchestrator",
            "urllib.request",
            "GEMINI_API_KEY",
        ]
        for fragment in forbidden_fragments:
            self.assertNotIn(fragment, cli_source)

    def test_cli_uses_project_task_ref_without_private_wrapper(self):
        cli_source = pathlib.Path("src/devflow/cli.py").read_text(encoding="utf-8")

        self.assertFalse(
            "def _task_ref(" in cli_source,
            "src/devflow/cli.py should use project_task_ref() directly instead of a private pass-through wrapper.",
        )
        self.assertIn("project_task_ref(", cli_source)

    def test_cli_uses_relative_path_without_private_wrapper(self):
        cli_source = pathlib.Path("src/devflow/cli.py").read_text(encoding="utf-8")

        self.assertFalse(
            "def _relative(" in cli_source,
            "src/devflow/cli.py should use relative_path() directly instead of a private pass-through wrapper.",
        )
        self.assertIn("relative_path(", cli_source)

    def test_only_shell_manual_and_local_ollama_patch_runtime_are_executable(self):
        """Contract test: remote provider adapters remain non-executable."""
        from devflow.control_room.agent_registry import (
            ADAPTER_MATURITY,
            EXPERIMENTAL_READONLY_ADAPTERS,
            LOCAL_PATCH_RUNTIME_ADAPTERS,
            PLANNED_NOT_EXECUTABLE_ADAPTERS,
            STABLE_RUNTIME_ADAPTERS,
            adapter_maturity,
        )

        self.assertEqual(
            ADAPTER_MATURITY,
            {
                "shell": "stable_runtime",
                "manual": "stable_runtime",
                "manual_packet": "experimental_readonly",
                "ollama_chat": "local_patch_runtime",
                "openai_responses": "planned_not_executable",
                "openai_compatible": "experimental_readonly",
                "anthropic_messages": "experimental_readonly",
                "gemini": "experimental_readonly",
                "openai_chat": "experimental_readonly",
                "hermes_profile": "planned_not_executable",
            },
        )
        self.assertEqual(adapter_maturity("unlisted-future-provider"), "planned_not_executable")

        self.assertEqual(
            set(STABLE_RUNTIME_ADAPTERS),
            {"shell", "manual"},
            "STABLE_RUNTIME_ADAPTERS must contain only 'shell' and 'manual' until provider "
            "adapters have tests, threat models, and explicit enable flags.",
        )
        self.assertEqual(set(LOCAL_PATCH_RUNTIME_ADAPTERS), {"ollama_chat"})
        self.assertEqual(
            set(EXPERIMENTAL_READONLY_ADAPTERS),
            {"manual_packet", "openai_compatible", "anthropic_messages", "gemini", "openai_chat"},
        )
        self.assertEqual(set(PLANNED_NOT_EXECUTABLE_ADAPTERS), {"hermes_profile", "openai_responses"})

        provider_adapters = {
            "ollama_chat", "openai_compatible", "anthropic_messages", "gemini", "openai_chat"
        }
        for adapter in provider_adapters:
            maturity = ADAPTER_MATURITY.get(adapter)
            self.assertNotEqual(
                maturity,
                "stable_runtime",
                f"Provider adapter '{adapter}' must not be stable_runtime. Got: {maturity}.",
            )

    def test_remote_provider_builtin_agents_are_disabled(self):
        """Contract test: provider-backed workers stay disabled by default."""
        from devflow.control_room.agent_registry import _builtin_agents

        provider_agent_ids = {
            "devflow-openai-worker",
            "devflow-anthropic-worker",
            "devflow-gemini-worker",
            "devflow-openai-compatible-worker",
            "devflow-openai-planner",
            "devflow-openai-reviewer",
        }
        agents = _builtin_agents()
        qwopus = agents.get("qwopus-implementer")
        self.assertIsNotNone(qwopus)
        self.assertFalse(qwopus.enabled)
        self.assertEqual(qwopus.adapter, "ollama_chat")
        self.assertEqual(qwopus.adapter_maturity, "local_patch_runtime")
        self.assertFalse(agents["devflow-ollama-worker"].enabled)
        for agent_id in provider_agent_ids:
            agent = agents.get(agent_id)
            self.assertIsNotNone(agent, f"Builtin agent '{agent_id}' not found")
            self.assertFalse(
                agent.enabled,
                f"Remote provider-backed agent '{agent_id}' must be disabled until it has "
                "its own tests, threat model, and explicit enable flag.",
            )

    def test_get_worker_adapter_rejects_non_stable(self):
        """Contract test: direct adapter lookup rejects non-stable adapters."""
        from devflow.control_room.worker_adapter import get_worker_adapter, UnsupportedWorkerAdapter

        non_stable = [
            "manual_packet",
            "ollama_chat",
            "openai_responses",
            "openai_chat",
            "anthropic_messages",
            "gemini",
            "openai_compatible",
            "hermes_profile",
        ]
        for adapter_name in non_stable:
            with self.assertRaises(UnsupportedWorkerAdapter, msg=f"Expected rejection of '{adapter_name}'"):
                get_worker_adapter(adapter_name)


if __name__ == "__main__":
    unittest.main()
