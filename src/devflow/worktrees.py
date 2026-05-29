"""Legacy shim — re-exports from devflow._legacy.worktrees."""
import sys
import devflow._legacy.worktrees as _legacy_module

sys.modules[__name__] = _legacy_module
