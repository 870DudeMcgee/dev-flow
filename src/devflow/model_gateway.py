"""Legacy shim — re-exports from devflow._legacy.model_gateway."""
import sys
import devflow._legacy.model_gateway as _legacy_module

sys.modules[__name__] = _legacy_module
