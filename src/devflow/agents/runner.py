"""Legacy shim — re-exports from devflow._legacy.agents.runner."""
import sys
import devflow._legacy.agents.runner as _legacy_module

sys.modules[__name__] = _legacy_module
