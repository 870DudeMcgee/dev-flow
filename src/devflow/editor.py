"""Legacy shim — re-exports from devflow._legacy.editor."""
import sys
import devflow._legacy.editor as _legacy_module

sys.modules[__name__] = _legacy_module
