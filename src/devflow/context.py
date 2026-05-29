"""Legacy shim — re-exports from devflow._legacy.context."""
import sys
import devflow._legacy.context as _legacy_module

sys.modules[__name__] = _legacy_module
