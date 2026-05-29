"""Legacy shim — re-exports from devflow._legacy.agents.skills."""
import sys
import devflow._legacy.agents.skills as _legacy_module

sys.modules[__name__] = _legacy_module
