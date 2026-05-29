"""Legacy shim — re-exports from devflow._legacy.failures."""
import sys
import devflow._legacy.failures as _legacy_module

sys.modules[__name__] = _legacy_module
