"""Legacy shim — re-exports from devflow._legacy.impact."""
import sys
import devflow._legacy.impact as _legacy_module

sys.modules[__name__] = _legacy_module
