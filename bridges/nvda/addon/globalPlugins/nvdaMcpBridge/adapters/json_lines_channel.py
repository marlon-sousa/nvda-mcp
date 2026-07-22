# nvdaMcpBridge adapters -- JsonLinesChannel: the MessageChannel over a Transport.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# ROLE: adapter. IMPLEMENTS the MessageChannel domain port.
# DEPENDS ON: the Transport adapter seam (adapters/ports/transport.py) -- never
#             on a concrete transport, which is what keeps this testable against
#             scripted bytes while the socket underneath stays a dumb leaf.
# BUILT BY: wiring.serve_transport (which pairs it with a concrete Transport).
#
# Every wire concern the domain must not know about lives here: reassembling
# chunks into newline-delimited frames, and JSON encode/decode via the shared
# protocol module. No NVDA import, so this stays fully type-checked.

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .. import protocol
from ..domain.ports.message_channel import TIMEOUT, ChannelClosed, MessageChannel, Timeout

if TYPE_CHECKING:
	from .ports.transport import Transport


class _LineReader:
	"""Private to this adapter: reassembles chunks into complete lines."""

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


class JsonLinesChannel(MessageChannel):
	"""Newline-delimited JSON messages over a byte transport."""

	def __init__(self, transport: Transport) -> None:
		self._transport = transport
		self._reader = _LineReader()

	def read_message(self) -> dict[str, Any] | Timeout:
		"""Next decoded message, or :data:`TIMEOUT`.

		Drains any line already buffered before touching the transport, so a
		message that already arrived is never lost to a timeout. Raises
		:class:`ChannelClosed` at EOF and
		:class:`protocol.ValidationError` for an unreadable line.
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
				raise ChannelClosed
			self._reader.feed(chunk)

	def write(self, message: Any) -> None:
		self._transport.sendall(protocol.encode_message(message))

	def close(self) -> None:
		self._transport.close()
