"""Legacy shim — re-exports from devflow._legacy.states."""
import sys
import devflow._legacy.states as _legacy_module

sys.modules[__name__] = _legacy_module
