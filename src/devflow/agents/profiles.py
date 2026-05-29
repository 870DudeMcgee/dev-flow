"""Legacy shim — re-exports from devflow._legacy.agents.profiles."""
import sys
import devflow._legacy.agents.profiles as _legacy_module

sys.modules[__name__] = _legacy_module
