"""Legacy shim — re-exports from devflow._legacy.manager."""
import sys
import devflow._legacy.manager as _legacy_module

sys.modules[__name__] = _legacy_module
