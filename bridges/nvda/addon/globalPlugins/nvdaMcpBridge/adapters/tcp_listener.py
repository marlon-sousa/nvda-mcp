# nvdaMcpBridge adapters -- TcpListener: the Listener leaf.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# ROLE: LEAF adapter. IMPLEMENTS the Listener seam (adapters/ports/listener.py)
#       by doing the real socket accept, and nothing else.
# USED BY: adapters/bridge_server.py, via the seam, never directly.
# BUILT BY: plugin.py in session C (loopback host + the default port).
#
# Loopback ONLY -- **Decided** (spec 0007, ROADMAP 9.1): remote TCP is remote
# keystroke injection and config writes, deferred behind its own security entry,
# so this binds 127.0.0.1 and never a routable address. listen(1) keeps a single
# session at a time (a second dial waits in the backlog or is refused).
#
# Decision-free by design: settimeout turns an idle accept into TimeoutError
# (socket.timeout IS TimeoutError since 3.10) so the server thread polls without
# a wakeup pipe, and close() from another thread makes a blocked accept raise --
# translated to ListenerClosed, the seam's contract, the only "logic" here and
# the direct analogue of SocketTransport reporting b"" at EOF.

from __future__ import annotations

import socket

from .ports.listener import Listener, ListenerClosed
from .ports.transport import Transport
from .socket_transport import DEFAULT_POLL_TIMEOUT, SocketTransport

#: Poll window for accept: how long it blocks before reporting TimeoutError, so
#: the server thread can notice a stop request. close() unblocks it sooner.
DEFAULT_ACCEPT_TIMEOUT: float = 0.5


class TcpListener(Listener):
	"""A loopback-only TCP listener yielding one connection at a time."""

	def __init__(
		self,
		host: str,
		port: int,
		*,
		accept_timeout: float = DEFAULT_ACCEPT_TIMEOUT,
		recv_timeout: float = DEFAULT_POLL_TIMEOUT,
	) -> None:
		self._host = host
		self._port = port
		self._accept_timeout = accept_timeout
		self._recv_timeout = recv_timeout
		self._sock: socket.socket | None = None
		self._endpoint = f"{host}:{port}"
		self._closed = False

	@property
	def endpoint(self) -> str:
		return self._endpoint

	def open(self) -> None:
		sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
		sock.bind((self._host, self._port))
		sock.listen(1)
		sock.settimeout(self._accept_timeout)
		# The bound port is only known now when the caller asked for port 0.
		bound_host, bound_port = sock.getsockname()[:2]
		self._endpoint = f"{bound_host}:{bound_port}"
		self._sock = sock

	def accept(self) -> Transport:
		if self._sock is None or self._closed:
			raise ListenerClosed
		try:
			conn, _ = self._sock.accept()
		except OSError:
			# A timeout is the idle poll; anything else on a closed socket is our
			# own close() unblocking the accept.
			if self._closed:
				raise ListenerClosed from None
			raise
		return SocketTransport(conn, poll_timeout=self._recv_timeout)

	def close(self) -> None:
		self._closed = True
		sock = self._sock
		self._sock = None
		if sock is not None:
			sock.close()
