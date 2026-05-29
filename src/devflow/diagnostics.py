"""Legacy shim — re-exports from devflow._legacy.diagnostics."""
import sys
import devflow._legacy.diagnostics as _legacy_module

sys.modules[__name__] = _legacy_module
