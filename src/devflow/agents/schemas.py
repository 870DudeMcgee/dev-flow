"""Legacy shim — re-exports from devflow._legacy.agents.schemas."""
import sys
import devflow._legacy.agents.schemas as _legacy_module

sys.modules[__name__] = _legacy_module
