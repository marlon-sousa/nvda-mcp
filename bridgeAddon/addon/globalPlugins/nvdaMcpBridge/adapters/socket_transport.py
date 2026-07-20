# nvdaMcpBridge adapters -- SocketTransport: the Transport leaf.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# ROLE: LEAF adapter. IMPLEMENTS the Transport seam (adapters/ports/transport.py)
#       by doing the real socket IO, and nothing else.
# USED BY: adapters/json_lines_channel.py, via the seam, never directly.
# BUILT BY: adapters/tcp_listener.py wraps each accepted connection in one; the
#           server dials one for the client end in the socket integration test.
#
# The dumbest networking file in the addon: spec 0002 shaped the Transport
# contract to match a timeout socket exactly, so there is no decision to make
# here and nothing to unit-test that the stdlib does not already guarantee.
# A blocking socket with settimeout raises socket.timeout when idle, and since
# Python 3.10 socket.timeout IS TimeoutError -- so the poll behaviour the seam
# promises falls out for free. Keep it decision-free: anything smarter belongs
# up in JsonLinesChannel.

from __future__ import annotations

import socket

from .ports.transport import Transport

#: How long recv blocks before reporting the idle poll timeout.
DEFAULT_POLL_TIMEOUT: float = 0.05


class SocketTransport(Transport):
	"""A byte pipe over one connected TCP socket, with a recv poll timeout."""

	def __init__(self, sock: socket.socket, *, poll_timeout: float = DEFAULT_POLL_TIMEOUT) -> None:
		self._sock = sock
		self._sock.settimeout(poll_timeout)

	def recv(self) -> bytes:
		"""Next chunk; ``b""`` at EOF; raises ``TimeoutError`` when idle.

		``settimeout`` in the constructor makes an idle read raise
		``socket.timeout`` (an alias of ``TimeoutError`` since 3.10), which is
		exactly the seam's contract, so it simply propagates.
		"""
		return self._sock.recv(4096)

	def sendall(self, data: bytes) -> None:
		self._sock.sendall(data)

	def close(self) -> None:
		self._sock.close()
