"""Legacy shim — re-exports from devflow._legacy.memory."""
import sys
import devflow._legacy.memory as _legacy_module

sys.modules[__name__] = _legacy_module
