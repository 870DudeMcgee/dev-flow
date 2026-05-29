"""Legacy shim — re-exports from devflow._legacy.task_commands."""
import sys
import devflow._legacy.task_commands as _legacy_module

sys.modules[__name__] = _legacy_module
