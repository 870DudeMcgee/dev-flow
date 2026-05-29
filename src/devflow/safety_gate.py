"""Legacy shim — re-exports from devflow._legacy.safety_gate."""
import sys
import devflow._legacy.safety_gate as _legacy_module

sys.modules[__name__] = _legacy_module
