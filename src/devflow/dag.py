"""Legacy shim — re-exports from devflow._legacy.dag."""
import sys
import devflow._legacy.dag as _legacy_module

sys.modules[__name__] = _legacy_module
