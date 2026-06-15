"""Legacy shim - re-exports from devflow.control_room.df_telegram_bridge."""
import sys

import devflow.control_room.df_telegram_bridge as _control_room_module

sys.modules[__name__] = _control_room_module
