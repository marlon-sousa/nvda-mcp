# Fakes implementing the bridge ports and adapter seams, for headless tests.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# Each fake subclasses the ABC it stands in for, so a forgotten method fails
# here exactly as it would for the real NVDA adapter. They are hand-written and
# STATEFUL rather than mocks, because the code under test drives its
# collaborators through real protocols (read loops, index reads, state
# transitions) and asserts on resulting behaviour -- a call-recorder would have
# to re-script return values per test and would exercise less. See AGENTS.md.
#
# Which fake for which test:
#   FakeChannel     -> the Session controller (scripts whole MESSAGES)
#   FakeTransport   -> the JsonLinesChannel adapter (scripts raw BYTES)
#   FakeFileWriter  -> the FileTranscript adapter (records lines, no filesystem)

from __future__ import annotations

from typing import Any, Final

from nvdaMcpBridge import protocol as p
from nvdaMcpBridge.adapters.ports.file_writer import FileWriter
from nvdaMcpBridge.adapters.ports.transport import Transport
from nvdaMcpBridge.domain.entities.braille_buffer import BrailleBuffer
from nvdaMcpBridge.domain.entities.speech_buffer import SpeechBuffer
from nvdaMcpBridge.domain.ports.adapter_factory import AdapterFactory, AdapterSet
from nvdaMcpBridge.domain.ports.clock import Clock
from nvdaMcpBridge.domain.ports.gesture_sender import GestureSender
from nvdaMcpBridge.domain.ports.message_channel import TIMEOUT, ChannelClosed, MessageChannel, Timeout
from nvdaMcpBridge.domain.ports.speech_source import SpeechSource
from nvdaMcpBridge.domain.ports.synth_swapper import SynthSwapper
from nvdaMcpBridge.domain.ports.transcript import Transcript


class FakeClock(Clock):
	"""A :class:`Clock` whose time only moves on demand.

	``sleep`` is an instant advance, which is what lets the domain's wait loops
	run to their deadline in microseconds. (This is why freezegun/time-machine
	would not help: they patch the global clock but leave ``time.sleep`` real.)
	"""

	def __init__(self, start: float = 0.0) -> None:
		self._now = start
		self.sleeps: list[float] = []

	def monotonic(self) -> float:
		return self._now

	def sleep(self, seconds: float) -> None:
		self.sleeps.append(seconds)
		self._now += seconds

	def advance(self, seconds: float) -> None:
		self._now += seconds


# -- scripted event queues ---------------------------------------------------


class _TimeoutEvent:
	__slots__ = ()


class _ClosedEvent:
	__slots__ = ()


#: Script entries: "the peer stayed quiet" and "the peer went away".
TIMEOUT_EVENT: Final = _TimeoutEvent()
CLOSED_EVENT: Final = _ClosedEvent()
#: Back-compat alias: at the byte level "closed" arrives as EOF.
EOF_EVENT: Final = CLOSED_EVENT


class _ScriptedQueue:
	"""Shared scripting behaviour for FakeChannel / FakeTransport.

	``on_empty`` decides the steady state once the script runs out: ``"closed"``
	ends the session; ``"timeout"`` keeps timing out and advancing the clock, so
	a heartbeat/inactivity deadline is eventually reached.
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
		if self._clock is not None:
			self._clock.advance(self._timeout_advance)


class FakeChannel(MessageChannel):
	"""Scripted :class:`MessageChannel` for testing the Session controller.

	The script is a list of whole messages (dicts), :data:`TIMEOUT_EVENT` and
	:data:`CLOSED_EVENT` -- no bytes, no JSON. Framing is the JsonLinesChannel
	adapter's problem and is tested there, which keeps session tests about the
	session.

	Two extra script entries make interleaving possible: a **callable** is
	invoked and skipped (use it to make NVDA "speak" at a chosen point mid
	session), and an **exception instance** is raised (e.g. a ValidationError,
	standing in for garbage on the wire).
	"""

	def __init__(
		self,
		events: list[Any] | None = None,
		*,
		clock: FakeClock | None = None,
		timeout_advance: float = 5.0,
		on_empty: str = "closed",
	) -> None:
		self._queue = _ScriptedQueue(list(events or []), clock, timeout_advance, on_empty)
		self.written: list[Any] = []
		self.closed = False

	def read_message(self) -> dict[str, Any] | Timeout:
		while True:
			event = self._queue.next_event()
			if isinstance(event, _TimeoutEvent):
				self._queue.tick_timeout()
				return TIMEOUT
			if isinstance(event, _ClosedEvent):
				raise ChannelClosed
			if isinstance(event, Exception):
				raise event
			if callable(event):
				# A side-effect step: run it and move on to the next event.
				event()  # pyright: ignore[reportUnknownVariableType]
				continue
			assert isinstance(event, dict)
			return event  # pyright: ignore[reportUnknownVariableType]

	def write(self, message: Any) -> None:
		self.written.append(message)

	def close(self) -> None:
		self.closed = True

	def responses(self) -> list[dict[str, Any]]:
		"""Everything written back, as plain dicts, in order."""
		return [p.to_dict(m) for m in self.written]


class FakeTransport(Transport):
	"""Scripted byte :class:`Transport` for testing the JsonLinesChannel adapter.

	The script is raw ``bytes`` chunks (split them to exercise reassembly),
	:data:`TIMEOUT_EVENT` (advances the clock and raises ``TimeoutError``, as a
	real idle socket does) and :data:`CLOSED_EVENT` (``recv`` returns ``b""``).
	"""

	def __init__(
		self,
		events: list[Any] | None = None,
		*,
		clock: FakeClock | None = None,
		timeout_advance: float = 5.0,
		on_empty: str = "closed",
	) -> None:
		self._queue = _ScriptedQueue(list(events or []), clock, timeout_advance, on_empty)
		self.outbox = bytearray()
		self.closed = False

	@classmethod
	def scripted(
		cls,
		requests: list[dict[str, Any]],
		*,
		clock: FakeClock | None = None,
		on_empty: str = "closed",
		timeout_advance: float = 5.0,
	) -> FakeTransport:
		"""Build a transport that delivers each request dict as one wire frame."""
		events: list[Any] = [p.encode_message(r) for r in requests]
		return cls(events, clock=clock, on_empty=on_empty, timeout_advance=timeout_advance)

	def recv(self) -> bytes:
		event = self._queue.next_event()
		if isinstance(event, _TimeoutEvent):
			self._queue.tick_timeout()
			raise TimeoutError
		if isinstance(event, _ClosedEvent):
			return b""
		assert isinstance(event, (bytes, bytearray))
		return bytes(event)

	def sendall(self, data: bytes) -> None:
		self.outbox.extend(data)

	def close(self) -> None:
		self.closed = True

	def responses(self) -> list[dict[str, Any]]:
		"""Decode every response frame written back, in order."""
		lines = bytes(self.outbox).splitlines()
		return [p.decode_message(line) for line in lines if line]


# -- adapter-seam fakes ------------------------------------------------------


class FakeFileWriter(FileWriter):
	"""In-memory :class:`FileWriter`: lets the transcript test assert exact lines."""

	def __init__(self, path: str = "session.log") -> None:
		self._path = path
		self.lines: list[str] = []
		self.opened = False
		self.closed = False

	@property
	def path(self) -> str:
		return self._path

	def open(self) -> None:
		self.opened = True

	def write_line(self, text: str) -> None:
		self.lines.append(text)

	def close(self) -> None:
		self.closed = True


# -- domain-port fakes -------------------------------------------------------


class FakeSpeechSource(SpeechSource):
	"""In-memory speech/braille capture the test drives directly."""

	def __init__(self, clock: FakeClock) -> None:
		self._speech = SpeechBuffer(clock)
		self._braille = BrailleBuffer(clock)
		self.started = False
		self.stopped = False

	@property
	def speech(self) -> SpeechBuffer:
		return self._speech

	@property
	def braille(self) -> BrailleBuffer:
		return self._braille

	def start(self) -> None:
		self.started = True

	def stop(self) -> None:
		self.stopped = True

	# test drivers -----------------------------------------------------------

	def emit_speech(self, *parts: Any) -> None:
		self._speech.append(list(parts))

	def emit_braille(self, text: str) -> None:
		self._braille.append(text)

	def finish_speaking(self) -> None:
		self._speech.notify_finished()


class FakeSynthSwapper(SynthSwapper):
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


class FakeGestureSender(GestureSender):
	"""Records emulated gestures; can reject named ids to test error paths."""

	def __init__(self, *, invalid: set[str] | None = None) -> None:
		self.sent: list[str] = []
		self._invalid = invalid or set()

	def send(self, gesture_id: str) -> None:
		if gesture_id in self._invalid:
			raise ValueError("unparseable gesture identifier")
		self.sent.append(gesture_id)


class FakeTranscript(Transcript):
	"""In-memory :class:`Transcript` recording each event as a string line."""

	def __init__(self, path: str = "session.log") -> None:
		self._path = path
		self.opened = False
		self.closed_reason: str | None = None
		self.lines: list[str] = []

	@property
	def path(self) -> str:
		return self._path

	def open(self) -> None:
		self.opened = True

	def session_opened(self, mode: str, synth: str) -> None:
		self.lines.append(f"SESSION OPEN mode={mode} synth={synth}")

	def synth_swapped(self, real_synth: str) -> None:
		self.lines.append(f"SYNTH SWAP saved={real_synth}")

	def synth_restored(self, real_synth: str) -> None:
		self.lines.append(f"SYNTH RESTORE -> {real_synth}")

	def gesture(self, gesture_id: str) -> None:
		self.lines.append(f"GESTURE {gesture_id}")

	def speech(self, text: str) -> None:
		self.lines.append(f"SPEECH {text!r}")

	def note(self, text: str) -> None:
		self.lines.append(f"NOTE {text}")

	def session_closed(self, reason: str) -> None:
		self.closed_reason = reason
		self.lines.append(f"SESSION CLOSE reason={reason}")


class FakeAdapterFactory(AdapterFactory):
	"""Hands back pre-built fakes, configured for the mode the session requests.

	Holds references the test can inspect after the run, and records which mode
	it was asked to build (the session's decoded ``hello`` mode).
	"""

	def __init__(
		self,
		speech_source: FakeSpeechSource,
		synth_swapper: FakeSynthSwapper,
		gesture_sender: FakeGestureSender,
	) -> None:
		self.speech_source = speech_source
		self.synth_swapper = synth_swapper
		self.gesture_sender = gesture_sender
		self.built_mode: p.CaptureMode | None = None

	def build(self, mode: p.CaptureMode) -> AdapterSet:
		self.built_mode = mode
		# Mode-specific wiring the real factory does at build time: silent mode
		# gets the exact synthDoneSpeaking finish signal.
		self.speech_source.speech.exact_finish = mode == p.CaptureMode.SILENT
		return AdapterSet(
			speech_source=self.speech_source,
			synth_swapper=self.synth_swapper,
			gesture_sender=self.gesture_sender,
		)
