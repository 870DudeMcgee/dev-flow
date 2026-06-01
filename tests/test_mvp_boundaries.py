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

    def test_only_shell_and_manual_are_stable_runtime(self):
        """Contract test: only shell and manual may be stable_runtime adapters."""
        from devflow.control_room.agent_registry import ADAPTER_MATURITY, STABLE_RUNTIME_ADAPTERS, adapter_maturity

        self.assertEqual(
            ADAPTER_MATURITY,
            {
                "shell": "stable_runtime",
                "manual": "stable_runtime",
                "manual_packet": "experimental_readonly",
                "ollama_chat": "experimental_readonly",
                "openai_responses": "planned_not_executable",
                "openai_compatible": "experimental_readonly",
                "anthropic_messages": "experimental_readonly",
                "gemini": "experimental_readonly",
                "openai_chat": "experimental_readonly",
            },
        )
        self.assertEqual(adapter_maturity("unlisted-future-provider"), "planned_not_executable")

        self.assertEqual(
            set(STABLE_RUNTIME_ADAPTERS),
            {"shell", "manual"},
            "STABLE_RUNTIME_ADAPTERS must contain only 'shell' and 'manual' until provider "
            "adapters have tests, threat models, and explicit enable flags.",
        )

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

    def test_provider_builtin_agents_are_disabled(self):
        """Contract test: all provider-backed builtin agents must be disabled by default."""
        from devflow.control_room.agent_registry import _builtin_agents

        provider_agent_ids = {
            "devflow-ollama-worker",
            "devflow-openai-worker",
            "devflow-anthropic-worker",
            "devflow-gemini-worker",
            "devflow-openai-compatible-worker",
            "devflow-openai-planner",
            "devflow-openai-reviewer",
        }
        agents = _builtin_agents()
        for agent_id in provider_agent_ids:
            agent = agents.get(agent_id)
            self.assertIsNotNone(agent, f"Builtin agent '{agent_id}' not found")
            self.assertFalse(
                agent.enabled,
                f"Provider-backed agent '{agent_id}' must be disabled until it has "
                "its own tests, threat model, and explicit enable flag.",
            )

    def test_get_worker_adapter_rejects_non_stable(self):
        """Contract test: get_worker_adapter must reject experimental/planned adapters."""
        from devflow.control_room.worker_adapter import get_worker_adapter, UnsupportedWorkerAdapter

        non_stable = [
            "manual_packet",
            "ollama_chat",
            "openai_responses",
            "openai_chat",
            "anthropic_messages",
            "gemini",
            "openai_compatible",
        ]
        for adapter_name in non_stable:
            with self.assertRaises(UnsupportedWorkerAdapter, msg=f"Expected rejection of '{adapter_name}'"):
                get_worker_adapter(adapter_name)


if __name__ == "__main__":
    unittest.main()
