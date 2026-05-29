"""Legacy shim — re-exports from devflow._legacy.safety."""
import sys
import devflow._legacy.safety as _legacy_module

sys.modules[__name__] = _legacy_module
