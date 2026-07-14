# nvdaMcpBridge -- JSON-lines framing over a byte transport.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# The bridge speaks the shared wire protocol as newline-delimited JSON over a
# loopback TCP socket. This module turns a raw byte transport into a stream of
# decoded request dicts and encoded response frames, so the session state
# machine never touches sockets directly and can be driven by an in-memory fake
# transport in tests.
#
# The transport is deliberately tiny (:class:`Transport`): ``recv`` returns a
# chunk, ``b""`` at EOF, and raises ``TimeoutError`` when no data arrived within
# its poll window (a real socket set with ``settimeout`` already does exactly
# this -- ``socket.timeout`` *is* ``TimeoutError`` on 3.10+). That timeout is
# how the session gets a chance to check its heartbeat / inactivity deadlines
# while otherwise blocked on the client.

from __future__ import annotations

from typing import Any, Final

from . import protocol


class ConnectionClosed(Exception):
	"""Raised by :meth:`Connection.read_message` when the peer closed the socket."""


class Timeout:
	"""Sentinel type returned by :meth:`Connection.read_message` on a poll timeout.

	Distinct from ``None`` (which is a valid JSON value) and from a closed
	connection (:class:`ConnectionClosed`), so the caller can tell "no data
	yet, go check your deadlines" apart from "peer is gone". A class (checked
	with :func:`isinstance`) rather than a bare object so the union
	``dict | Timeout`` narrows cleanly under a strict type checker.
	"""

	__slots__ = ()

	def __repr__(self) -> str:  # pragma: no cover - debug aid
		return "TIMEOUT"


#: The single :class:`Timeout` instance; test with ``isinstance(msg, Timeout)``.
TIMEOUT: Final = Timeout()


class Transport:
	"""Structural interface for the byte pipe a :class:`Connection` wraps.

	Documented as a base for clarity; any object with these three methods (a
	socket wrapper in production, an in-memory fake in tests) is accepted.
	"""

	def recv(self) -> bytes:
		"""Return the next chunk, ``b""`` at EOF; raise ``TimeoutError`` if idle."""
		raise NotImplementedError

	def sendall(self, data: bytes) -> None:
		raise NotImplementedError

	def close(self) -> None:
		raise NotImplementedError


class _LineReader:
	"""Reassembles ``recv`` chunks into complete ``\\n``-terminated lines."""

	def __init__(self) -> None:
		self._buffer = bytearray()

	def feed(self, chunk: bytes) -> None:
		self._buffer.extend(chunk)

	def next_line(self) -> bytes | None:
		"""Pop one complete line (without the newline), or ``None`` if incomplete."""
		newline = self._buffer.find(b"\n")
		if newline < 0:
			return None
		line = bytes(self._buffer[:newline])
		del self._buffer[: newline + 1]
		return line


class Connection:
	"""A framed request/response channel over a :class:`Transport`."""

	def __init__(self, transport: Transport) -> None:
		self._transport = transport
		self._reader = _LineReader()

	def read_message(self) -> dict[str, Any] | Timeout:
		"""Return the next decoded request dict, or :data:`TIMEOUT`.

		Drains any line already buffered before reading more from the
		transport, so no message is lost across a timeout. Raises
		:class:`ConnectionClosed` at EOF and
		:class:`protocol.ValidationError` for a malformed JSON line.
		"""
		while True:
			line = self._reader.next_line()
			if line is not None:
				return protocol.decode_message(line)
			try:
				chunk = self._transport.recv()
			except TimeoutError:
				return TIMEOUT
			if chunk == b"":
				raise ConnectionClosed
			self._reader.feed(chunk)

	def write(self, obj: Any) -> None:
		"""Encode ``obj`` (a wire dataclass or dict) and send it as one line."""
		self._transport.sendall(protocol.encode_message(obj))

	def close(self) -> None:
		self._transport.close()
