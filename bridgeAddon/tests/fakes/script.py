# nvdaMcpBridge tests -- shared scaffolding for fakes that replay a script.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# Not a fake of any one port: this is the "replay a queue of events" behaviour
# that every read-side fake needs, at whichever level it sits. FakeTransport
# replays bytes; the session's FakeChannel replays whole messages. Both need the
# same three ideas -- a scripted event, "the peer stayed quiet", "the peer went
# away" -- so they share them rather than each inventing their own.

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final

if TYPE_CHECKING:
	from .clock import FakeClock


class TimeoutEvent:
	"""The peer stayed quiet: the reader should report a poll timeout.

	Public because each fake must recognise it -- ``isinstance`` against the type
	rather than ``is`` against the singleton, so the union narrows for a strict
	type checker. Scripts use the :data:`TIMEOUT_EVENT` instance.
	"""

	__slots__ = ()


class ClosedEvent:
	"""The peer went away: EOF at the byte level, ChannelClosed at the message level."""

	__slots__ = ()


TIMEOUT_EVENT: Final = TimeoutEvent()
CLOSED_EVENT: Final = ClosedEvent()


class ScriptedQueue:
	"""A queue of scripted events with a defined steady state once it empties.

	``on_empty`` decides what happens after the script runs out: ``"closed"``
	(default) ends the session, so a test that forgets to terminate its script
	still finishes; ``"timeout"`` keeps timing out and advancing the clock, which
	is how a heartbeat / inactivity deadline is eventually reached.
	"""

	def __init__(
		self,
		events: list[Any],
		clock: FakeClock | None,
		timeout_advance: float,
		on_empty: str,
	) -> None:
		self._events = list(events)
		self._clock = clock
		self._timeout_advance = timeout_advance
		self._on_empty = on_empty

	def next_event(self) -> Any:
		if self._events:
			return self._events.pop(0)
		return TIMEOUT_EVENT if self._on_empty == "timeout" else CLOSED_EVENT

	def tick_timeout(self) -> None:
		"""Advance the clock as a real idle poll would have."""
		if self._clock is not None:
			self._clock.advance(self._timeout_advance)
