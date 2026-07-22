# nvdaMcpBridge domain -- ConnectionMode: the transport the bridge listens on.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# ROLE: entity. A StrEnum the domain, views, and adapters all import (it lives in
#       domain/ so it stays pure; protocol.py does NOT need it -- the wire does
#       not know about transports).
# USED BY: domain/ports/bridge_config.py (the persistence port), views/bridge_dialog.py
#          (the mode combo), adapters/ini_bridge_config.py (the .ini adapter), and
#          plugin.py (config-driven listener choice).
# REMOTE_TCP is defined but unreachable from the UI until its security entry lands
# (ROADMAP 9.1b note); the combo shows it greyed out.

from __future__ import annotations

from enum import StrEnum
from typing import Final


class ConnectionMode(StrEnum):
	"""How the bridge accepts connections -- the transport, not the wire."""

	NAMED_PIPE = "namedPipe"
	LOOPBACK_TCP = "loopbackTcp"
	REMOTE_TCP = "remoteTcp"  # defined but unreachable from the UI until its security entry lands


DEFAULT: Final = ConnectionMode.NAMED_PIPE
