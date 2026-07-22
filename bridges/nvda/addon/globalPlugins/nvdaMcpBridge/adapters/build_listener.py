# nvdaMcpBridge adapters -- build_listener: the single mode→Listener factory.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# ROLE: a pure factory function (no NVDA imports). Maps a ConnectionMode to the
#       matching Listener leaf so the mapping lives in one place.
# USED BY: plugin.py (initial listener on load, start_server), and later
#          views/bridge_dialog.py (imported from here so the dialog calls the
#          same factory).
# BUILT BY: no one -- plain function, called directly.

from __future__ import annotations

from ..domain.entities.connection_mode import ConnectionMode
from .named_pipe_listener import NamedPipeListener
from .ports.listener import Listener
from .tcp_listener import TcpListener
from .. import protocol


def build_listener(mode: ConnectionMode) -> Listener:
	"""The single mode→Listener factory. Pure: neither leaf constructor imports NVDA."""
	if mode is ConnectionMode.NAMED_PIPE:
		return NamedPipeListener(protocol.DEFAULT_PIPE_NAME)
	if mode is ConnectionMode.LOOPBACK_TCP:
		return TcpListener("127.0.0.1", protocol.DEFAULT_PORT)
	raise ValueError(f"Unsupported connection mode: {mode}")
