# nvdaMcpBridge domain -- JSON-lines framing over the Transport port.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# The bridge speaks the shared wire protocol as newline-delimited JSON. This
# module turns the raw byte :class:`~..domain.ports.Transport` into a stream of
# decoded request dicts and encoded response frames, so the session state
# machine never touches sockets directly and can be driven by an in-memory fake
# transport in tests.
#
# ``Transport.recv`` raises ``TimeoutError`` when idle (a real socket with
# ``settimeout`` already does); :meth:`Connection.read_message` turns that into
# the :data:`TIMEOUT` sentinel, which is the session's cue to check its
# heartbeat / inactivity deadlines while otherwise blocked on the client.

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final

from .. import protocol

if TYPE_CHECKING:
	from .ports import Transport


class ConnectionClosed(Exception):
	"""Raised by :meth:`Connection.read_message` when the peer closed the socket."""


class Timeout:
	"""Sentinel type returned by :meth:`Connection.read_message` on a poll timeout.

	Distinct from ``None`` (a valid JSON value) and from a closed connection
	(:class:`ConnectionClosed`), so the caller can tell "no data yet, go check
	your deadlines" apart from "peer is gone". A class (checked with
	:func:`isinstance`) rather than a bare object so the union ``dict | Timeout``
	narrows cleanly under a strict type checker.
	"""

	__slots__ = ()

	def __repr__(self) -> str:  # pragma: no cover - debug aid
		return "TIMEOUT"


#: The single :class:`Timeout` instance; test with ``isinstance(msg, Timeout)``.
TIMEOUT: Final = Timeout()


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
	"""A framed request/response channel over a :class:`~..domain.ports.Transport`."""

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
