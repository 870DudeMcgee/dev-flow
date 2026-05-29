"""Legacy shim — re-exports from devflow._legacy.artifacts."""
import sys
import devflow._legacy.artifacts as _legacy_module

sys.modules[__name__] = _legacy_module
