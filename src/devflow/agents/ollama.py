"""Legacy shim — re-exports from devflow._legacy.agents.ollama."""
import sys
import devflow._legacy.agents.ollama as _legacy_module

sys.modules[__name__] = _legacy_module
