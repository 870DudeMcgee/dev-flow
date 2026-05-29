"""Legacy shim — re-exports from devflow._legacy.repo_map."""
import sys
import devflow._legacy.repo_map as _legacy_module

sys.modules[__name__] = _legacy_module
