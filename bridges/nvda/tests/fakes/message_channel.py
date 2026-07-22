# nvdaMcpBridge tests -- FakeChannel, standing in for the MessageChannel port.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# FAKES: domain/ports/message_channel.py
#
# The session's I/O double: it scripts WHOLE messages (dicts), not bytes -- the
# byte level is JsonLinesChannel's job, proven once in test_json_lines_channel.
# Script entries reuse fakes/script.py: a ``dict`` is a message; TIMEOUT_EVENT is
# a quiet poll (advances the clock as a real idle socket would); CLOSED_EVENT is
# the peer going away (ChannelClosed); an ``Exception`` instance is raised as-is,
# which is how a test drives the "unreadable line" path (a protocol.ValidationError
# straight from read_message). Everything written back is recorded for assertions.

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from nvdaMcpBridge import protocol as p
from nvdaMcpBridge.domain.ports.message_channel import TIMEOUT, ChannelClosed, MessageChannel, Timeout

from .script import ClosedEvent, ScriptedQueue, TimeoutEvent

if TYPE_CHECKING:
	from .clock import FakeClock


class FakeChannel(MessageChannel):
	"""Replays a scripted stream of whole messages and records the replies."""

	def __init__(
		self,
		events: list[Any] | None = None,
		*,
		clock: FakeClock | None = None,
		timeout_advance: float = 5.0,
		on_empty: str = "closed",
	) -> None:
		self._queue = ScriptedQueue(list(events or []), clock, timeout_advance, on_empty)
		self.sent: list[Any] = []
		self.closed = False

	def read_message(self) -> dict[str, Any] | Timeout:
		event = self._queue.next_event()
		if isinstance(event, TimeoutEvent):
			self._queue.tick_timeout()
			return TIMEOUT
		if isinstance(event, ClosedEvent):
			raise ChannelClosed
		if isinstance(event, Exception):
			raise event
		assert isinstance(event, dict)
		return cast("dict[str, Any]", event)

	def write(self, message: Any) -> None:
		self.sent.append(message)

	def close(self) -> None:
		self.closed = True

	def responses(self) -> list[dict[str, Any]]:
		"""Every reply written back, decoded to plain dicts, in order."""
		return [p.to_dict(m) for m in self.sent]
