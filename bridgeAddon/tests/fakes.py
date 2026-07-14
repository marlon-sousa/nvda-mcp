# Fakes implementing the bridge adapter Protocols, for headless tests.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# These stand in for NVDA and the socket so the whole session state machine can
# be exercised deterministically: the clock only advances when told (or on a
# scripted transport timeout), so heartbeat / inactivity / wait timeouts are
# tested without ever sleeping in real time; the transport replays a scripted
# sequence of frames, timeouts and EOF and records every response written back.

from __future__ import annotations

from typing import Any, Final

from nvdaMcpBridge import protocol as p
from nvdaMcpBridge.speech_buffer import BrailleBuffer, SpeechBuffer


class FakeClock:
	"""A :class:`~nvdaMcpBridge.adapters.Clock` whose time only moves on demand."""

	def __init__(self, start: float = 0.0) -> None:
		self._now = start
		self.sleeps: list[float] = []

	def monotonic(self) -> float:
		return self._now

	def sleep(self, seconds: float) -> None:
		# A fake sleep is an instant clock advance -- wait loops make progress
		# toward their deadline without any real delay.
		self.sleeps.append(seconds)
		self._now += seconds

	def advance(self, seconds: float) -> None:
		self._now += seconds


# -- transport ---------------------------------------------------------------


class _TimeoutEvent:
	__slots__ = ()


class _EofEvent:
	__slots__ = ()


TIMEOUT_EVENT: Final = _TimeoutEvent()
EOF_EVENT: Final = _EofEvent()


class FakeTransport:
	"""Scriptable byte transport for :class:`~nvdaMcpBridge.framing.Connection`.

	``events`` is a queue of: ``bytes`` (delivered by one ``recv``), a
	:data:`TIMEOUT_EVENT` (advances the clock and raises ``TimeoutError``, as a
	real idle socket does) or an :data:`EOF_EVENT` (``recv`` returns ``b""``).
	When the queue empties, ``on_empty`` decides the steady state: ``"eof"``
	(default) closes the connection; ``"timeout"`` keeps timing out and
	advancing the clock, so a heartbeat/inactivity deadline is eventually hit.
	"""

	def __init__(
		self,
		events: list[Any] | None = None,
		*,
		clock: FakeClock | None = None,
		timeout_advance: float = 5.0,
		on_empty: str = "eof",
	) -> None:
		self._events: list[Any] = list(events or [])
		self._clock = clock
		self._timeout_advance = timeout_advance
		self._on_empty = on_empty
		self.outbox = bytearray()
		self.closed = False

	@classmethod
	def scripted(
		cls,
		requests: list[dict[str, Any]],
		*,
		clock: FakeClock | None = None,
		on_empty: str = "eof",
		timeout_advance: float = 5.0,
	) -> FakeTransport:
		"""Build a transport that delivers each request dict as one wire frame."""
		events: list[Any] = [p.encode_message(r) for r in requests]
		return cls(events, clock=clock, on_empty=on_empty, timeout_advance=timeout_advance)

	def recv(self) -> bytes:
		event = self._events.pop(0) if self._events else self._empty_event()
		if isinstance(event, _TimeoutEvent):
			if self._clock is not None:
				self._clock.advance(self._timeout_advance)
			raise TimeoutError
		if isinstance(event, _EofEvent):
			return b""
		assert isinstance(event, (bytes, bytearray))
		return bytes(event)

	def _empty_event(self) -> Any:
		return TIMEOUT_EVENT if self._on_empty == "timeout" else EOF_EVENT

	def sendall(self, data: bytes) -> None:
		self.outbox.extend(data)

	def close(self) -> None:
		self.closed = True

	def responses(self) -> list[dict[str, Any]]:
		"""Decode every response frame written back, in order."""
		lines = bytes(self.outbox).splitlines()
		return [p.decode_message(line) for line in lines if line]


# -- adapter fakes -----------------------------------------------------------


class FakeSpeechSource:
	"""In-memory speech/braille capture the test drives directly."""

	def __init__(self, clock: FakeClock) -> None:
		self._speech = SpeechBuffer(clock)
		self._braille = BrailleBuffer(clock)
		self.started_mode: str | None = None
		self.stopped = False

	@property
	def speech(self) -> SpeechBuffer:
		return self._speech

	@property
	def braille(self) -> BrailleBuffer:
		return self._braille

	def start(self, mode: str) -> None:
		self.started_mode = mode
		self._speech.exact_finish = mode == p.CaptureMode.SILENT

	def stop(self) -> None:
		self.stopped = True

	# test drivers -----------------------------------------------------------

	def emit_speech(self, *parts: Any) -> None:
		self._speech.append(list(parts))

	def emit_braille(self, text: str) -> None:
		self._braille.append(text)

	def finish_speaking(self) -> None:
		self._speech.notify_finished()


class FakeSynthSwapper:
	"""Records swap/restore so tests can assert restoration on every path."""

	def __init__(self, real_synth_name: str = "espeak", *, raise_on_restore: bool = False) -> None:
		self._real = real_synth_name
		self._swapped = False
		self._raise_on_restore = raise_on_restore
		self.swap_count = 0
		self.restore_count = 0

	@property
	def real_synth_name(self) -> str:
		return self._real

	@property
	def swapped(self) -> bool:
		return self._swapped

	def swap_in(self) -> None:
		self._swapped = True
		self.swap_count += 1

	def restore(self) -> None:
		self.restore_count += 1
		self._swapped = False
		if self._raise_on_restore:
			raise RuntimeError("simulated restore failure")


class FakeGestureSender:
	"""Records emulated gestures; can reject named ids to test error paths."""

	def __init__(self, *, invalid: set[str] | None = None) -> None:
		self.sent: list[str] = []
		self._invalid = invalid or set()

	def send(self, gesture_id: str) -> None:
		if gesture_id in self._invalid:
			raise ValueError("unparseable gesture identifier")
		self.sent.append(gesture_id)
