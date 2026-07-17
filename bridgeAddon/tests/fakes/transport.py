# nvdaMcpBridge tests -- FakeTransport, standing in for the Transport seam.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# FAKES: adapters/ports/transport.py
#
# The only fake that deals in bytes. It exists so JsonLinesChannel's framing can
# be driven precisely -- split a frame across chunks, pack two into one, go
# quiet, hang up -- without a socket. Everything above the channel scripts whole
# messages instead. Script entries come from fakes/script.py; import them from
# there (no re-export facades here either).

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from nvdaMcpBridge import protocol as p
from nvdaMcpBridge.adapters.ports.transport import Transport

from .script import ClosedEvent, ScriptedQueue, TimeoutEvent

if TYPE_CHECKING:
	from .clock import FakeClock


class FakeTransport(Transport):
	"""Replays a scripted byte stream.

	Script entries: ``bytes`` (one ``recv`` returns them), ``TIMEOUT_EVENT``
	(advances the clock and raises ``TimeoutError``, as a real idle socket does)
	and ``CLOSED_EVENT`` (``recv`` returns ``b""``). Everything written back is
	recorded, decodable via :meth:`responses`.
	"""

	def __init__(
		self,
		events: list[Any] | None = None,
		*,
		clock: FakeClock | None = None,
		timeout_advance: float = 5.0,
		on_empty: str = "closed",
	) -> None:
		self._queue = ScriptedQueue(list(events or []), clock, timeout_advance, on_empty)
		self.outbox = bytearray()
		self.closed = False

	def recv(self) -> bytes:
		event = self._queue.next_event()
		if isinstance(event, TimeoutEvent):
			self._queue.tick_timeout()
			raise TimeoutError
		if isinstance(event, ClosedEvent):
			return b""
		assert isinstance(event, (bytes, bytearray))
		return bytes(event)

	def sendall(self, data: bytes) -> None:
		self.outbox.extend(data)

	def close(self) -> None:
		self.closed = True

	def responses(self) -> list[dict[str, Any]]:
		"""Decode every frame written back, in order."""
		lines = bytes(self.outbox).splitlines()
		return [p.decode_message(line) for line in lines if line]
