"""Legacy shim — re-exports from devflow._legacy.workspace."""
import sys
import devflow._legacy.workspace as _legacy_module

sys.modules[__name__] = _legacy_module
