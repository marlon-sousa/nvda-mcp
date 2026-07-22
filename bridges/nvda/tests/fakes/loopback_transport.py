# nvdaMcpBridge tests -- LoopbackTransport, a connected pair of Transport ends.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# FAKES: adapters/ports/transport.py
#
# The last piece needed to run the REAL channel stack (JsonLinesChannel over a
# Transport) end to end without a socket: two transports wired back to back over
# thread-safe queues, so one end's sendall becomes the other end's recv. It
# honours the Transport contract exactly -- recv raises TimeoutError when idle
# (so the Session's poll loop keeps checking its deadlines) and returns b"" once
# the peer has closed -- which is why the same session code runs over this and,
# in session C, over a real socket.

from __future__ import annotations

import queue

from nvdaMcpBridge.adapters.ports.transport import Transport


class _Eof:
	"""Sentinel put on the queue by close(), surfaced to the peer as EOF."""

	__slots__ = ()


_EOF = _Eof()


class LoopbackTransport(Transport):
	"""One end of a back-to-back transport pair. Build pairs with :func:`loopback_pair`."""

	def __init__(
		self,
		incoming: queue.Queue[bytes | _Eof],
		outgoing: queue.Queue[bytes | _Eof],
		*,
		poll_timeout: float = 0.05,
	) -> None:
		self._incoming = incoming
		self._outgoing = outgoing
		self._poll_timeout = poll_timeout
		self._eof = False

	def recv(self) -> bytes:
		if self._eof:
			return b""
		try:
			item = self._incoming.get(timeout=self._poll_timeout)
		except queue.Empty:
			raise TimeoutError from None
		if isinstance(item, _Eof):
			self._eof = True
			return b""
		return item

	def sendall(self, data: bytes) -> None:
		self._outgoing.put(data)

	def close(self) -> None:
		self._outgoing.put(_EOF)


def loopback_pair(*, poll_timeout: float = 0.05) -> tuple[LoopbackTransport, LoopbackTransport]:
	"""A (bridge, agent) pair: each end's writes are the other's reads."""
	a_to_b: queue.Queue[bytes | _Eof] = queue.Queue()
	b_to_a: queue.Queue[bytes | _Eof] = queue.Queue()
	bridge = LoopbackTransport(incoming=a_to_b, outgoing=b_to_a, poll_timeout=poll_timeout)
	agent = LoopbackTransport(incoming=b_to_a, outgoing=a_to_b, poll_timeout=poll_timeout)
	return bridge, agent
