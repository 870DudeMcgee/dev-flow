"""Legacy shim — re-exports from devflow._legacy.orchestrator_agentic."""
import sys
import devflow._legacy.orchestrator_agentic as _legacy_module

sys.modules[__name__] = _legacy_module
