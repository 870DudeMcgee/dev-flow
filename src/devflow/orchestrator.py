"""Legacy shim — re-exports from devflow._legacy.orchestrator."""
import sys
import devflow._legacy.orchestrator as _legacy_module

sys.modules[__name__] = _legacy_module
