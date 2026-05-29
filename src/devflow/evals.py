"""Legacy shim — re-exports from devflow._legacy.evals."""
import sys
import devflow._legacy.evals as _legacy_module

sys.modules[__name__] = _legacy_module
