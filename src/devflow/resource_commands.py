"""Legacy shim — re-exports from devflow._legacy.resource_commands."""
import sys
import devflow._legacy.resource_commands as _legacy_module

sys.modules[__name__] = _legacy_module
