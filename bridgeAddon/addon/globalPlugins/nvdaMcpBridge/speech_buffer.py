# nvdaMcpBridge -- indexed, thread-safe speech and braille buffers.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# A stdlib-only port of the buffer half of NVDA's own ``NVDASpyLib``
# (``tests/system/libraries/SystemTestSpy/speechSpyGlobalPlugin.py``). Speech
# and braille are captured into append-only, index-addressed lists guarded by
# an RLock. Index-based access -- "everything since index N", "wait for text
# after index N" -- is what makes assertions race-free: the agent bookmarks an
# index (``getNextSpeechIndex``), sends a gesture, then reads/waits from that
# bookmark, so background chatter that arrived earlier can never be mistaken for
# the response to its action.
#
# Index convention (kept identical to NVDASpyLib): a buffer starts with one
# empty sentinel entry at index 0, so ``[-1]`` is always valid and the first
# real capture lands at index 1. ``next_index()`` is the index the next capture
# will occupy; it is the bookmark an agent takes before an action.

from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
	from .adapters import Clock

#: Live mode has no exact "speech finished" signal, so we treat speech as
#: finished once this many seconds pass with no new sequence (NVDASpyLib's
#: ``SPEECH_HAS_FINISHED_SECONDS``). Silent mode ignores this and uses the
#: spy synth's ``synthDoneSpeaking`` instead (see :meth:`SpeechBuffer.notify_finished`).
SPEECH_FINISHED_SECONDS: float = 1.0

#: Poll cadence for the wait loops. Small enough to feel instant, large enough
#: not to spin. Fakes make :meth:`Clock.sleep` a no-op so tests never pause.
_POLL_INTERVAL: float = 0.03


class _IndexedBuffer:
	"""Common index bookkeeping for the speech and braille buffers.

	Subclasses supply :meth:`_render` (entry -> displayable string) and decide
	what an entry is; this base owns the lock, the sentinel, append timing and
	the index-range reads.
	"""

	def __init__(self, clock: Clock) -> None:
		self._clock = clock
		self._lock = threading.RLock()
		self._entries: list[Any] = [self._sentinel()]
		self._last_time: float = clock.monotonic()

	def _sentinel(self) -> Any:
		"""The empty entry seeded at index 0. Must render to ``""``."""
		raise NotImplementedError

	def _render(self, entry: Any) -> str:
		raise NotImplementedError

	def _append(self, entry: Any) -> None:
		with self._lock:
			self._entries.append(entry)
			self._last_time = self._clock.monotonic()

	def last_index(self) -> int:
		"""Index of the most recent entry (0 when only the sentinel is present)."""
		with self._lock:
			return len(self._entries) - 1

	def next_index(self) -> int:
		"""Index the next captured entry will occupy; the agent's bookmark."""
		with self._lock:
			return len(self._entries)

	def get_last(self) -> tuple[str, int]:
		"""``(rendered text, index)`` of the most recent entry."""
		with self._lock:
			index = len(self._entries) - 1
			return self._render(self._entries[index]), index

	def get_since(self, index: int) -> tuple[str, int, int]:
		"""Rendered text of every entry from ``index`` to now.

		Returns ``(text, fromIndex, toIndex)`` where the range is half-open
		``[fromIndex, toIndex)``; ``text`` joins the non-empty entries with
		newlines. A negative or out-of-range ``index`` is clamped into range so
		a stale bookmark can never raise.
		"""
		with self._lock:
			start = max(0, index)
			rendered = [self._render(e) for e in self._entries[start:]]
			text = "\n".join(t for t in rendered if t and not t.isspace())
			return text, start, len(self._entries)

	def _wait(self, predicate: Callable[[], bool], timeout: float) -> bool:
		"""Poll ``predicate`` until it is true or ``timeout`` seconds elapse.

		Checks once immediately (so a zero timeout still evaluates the current
		state), then sleeps the clock between polls. Returns whether it was met.
		"""
		deadline = self._clock.monotonic() + max(0.0, timeout)
		while True:
			if predicate():
				return True
			if self._clock.monotonic() >= deadline:
				return False
			self._clock.sleep(_POLL_INTERVAL)


def _join_speech(sequence: Any) -> str:
	"""Join the plain-string parts of a speech sequence, trimming whitespace.

	NVDA speech sequences interleave ``str`` fragments with ``SpeechCommand``
	objects (pitch, index, callbacks, ...). Only the strings are spoken words,
	so those are all we capture.
	"""
	if not isinstance(sequence, (list, tuple)):
		return ""
	parts = [c for c in sequence if isinstance(c, str)]  # pyright: ignore[reportUnknownVariableType]
	return "".join(parts).strip()


class SpeechBuffer(_IndexedBuffer):
	"""Indexed capture of NVDA speech sequences with wait-for / wait-to-finish.

	``exact_finish`` selects how "speech has finished" is decided: silent mode
	sets it true and drives :meth:`notify_finished` from the spy synth's
	``synthDoneSpeaking``; live mode leaves it false and falls back to the
	elapsed-time heuristic.
	"""

	def __init__(self, clock: Clock, *, exact_finish: bool = False) -> None:
		super().__init__(clock)
		#: Flipped by the speech source at ``start(mode)``.
		self.exact_finish: bool = exact_finish
		self._speaking: bool = False
		self._observer: Callable[[str], None] | None = None

	def _sentinel(self) -> Any:
		return [""]

	def _render(self, entry: Any) -> str:
		return _join_speech(entry)

	def set_observer(self, observer: Callable[[str], None] | None) -> None:
		"""Register a callback fired (outside the lock) for each appended text.

		The session wires this to the transcript so captured speech is logged
		bridge-side even if the agent never fetches it.
		"""
		self._observer = observer

	def append(self, sequence: Any) -> None:
		"""Record a captured speech sequence; called from NVDA's speech path."""
		with self._lock:
			self._entries.append(sequence)
			self._last_time = self._clock.monotonic()
			self._speaking = True
			text = _join_speech(sequence)
		if self._observer is not None and text:
			self._observer(text)

	def notify_finished(self) -> None:
		"""Exact "speech finished" signal (silent mode: ``synthDoneSpeaking``)."""
		with self._lock:
			self._speaking = False

	def index_of(self, text: str, after_index: int | None = None) -> int:
		"""First index at/after ``after_index`` whose text contains ``text``.

		``after_index`` is exclusive (search starts at ``after_index + 1``),
		matching NVDASpyLib. Returns ``-1`` when not found.
		"""
		first = 0 if after_index is None else after_index + 1
		with self._lock:
			for offset, entry in enumerate(self._entries[first:]):
				if text in self._render(entry):
					return first + offset
		return -1

	def wait_for(self, text: str, after_index: int | None, timeout: float) -> tuple[bool, int, str]:
		"""Block until ``text`` is spoken after ``after_index`` or ``timeout``.

		Returns ``(found, index, text)``. On a miss, ``index`` is the current
		:meth:`next_index` (a fresh bookmark) and ``text`` is empty.
		"""
		found_index = -1

		def _seen() -> bool:
			nonlocal found_index
			found_index = self.index_of(text, after_index)
			return found_index >= 0

		if self._wait(_seen, timeout):
			with self._lock:
				return True, found_index, self._render(self._entries[found_index])
		return False, self.next_index(), ""

	def wait_to_finish(self, timeout: float) -> bool:
		"""Block until NVDA has stopped speaking, or ``timeout`` elapses."""
		return self._wait(self._has_finished, timeout)

	def _has_finished(self) -> bool:
		with self._lock:
			if self.exact_finish:
				return not self._speaking
			return (self._clock.monotonic() - self._last_time) > SPEECH_FINISHED_SECONDS


class BrailleBuffer(_IndexedBuffer):
	"""Indexed capture of raw braille text, de-duplicating consecutive repeats.

	NVDA rewrites the whole braille window on every update; identical
	consecutive writes are dropped (as NVDASpyLib does) so the buffer records
	genuine changes rather than refreshes.
	"""

	def _sentinel(self) -> Any:
		return ""

	def _render(self, entry: Any) -> str:
		return entry if isinstance(entry, str) else ""

	def append(self, raw_text: str) -> None:
		"""Record a braille update; empty or unchanged text is ignored."""
		text = raw_text.strip()
		if not text:
			return
		with self._lock:
			if self._entries and self._entries[-1] == text:
				return
			self._entries.append(text)
			self._last_time = self._clock.monotonic()
