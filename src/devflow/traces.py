"""Legacy shim — re-exports from devflow._legacy.traces."""
import sys
import devflow._legacy.traces as _legacy_module

sys.modules[__name__] = _legacy_module
