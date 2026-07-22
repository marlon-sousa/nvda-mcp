# nvdaMcpBridge domain -- SpeechBuffer: indexed capture of what NVDA speaks.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# ROLE: entity. The bridge's central subject matter.
# FED BY: the SpeechSource port's implementation (the spy synth in silent mode,
#         the pre_speechQueued hook in live mode) calling append/notify_finished.
# READ BY: the Session controller, answering getSpeech / waitForSpeech / ...
# DEPENDS ON: the Clock port (injected via IndexedBuffer).

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

from .indexed_buffer import IndexedBuffer

if TYPE_CHECKING:
	from ..ports.clock import Clock

#: Live mode has no exact "speech finished" signal, so we treat speech as
#: finished once this many seconds pass with no new sequence (NVDASpyLib's
#: ``SPEECH_HAS_FINISHED_SECONDS``). Silent mode ignores this and uses the spy
#: synth's ``synthDoneSpeaking`` instead (see :meth:`SpeechBuffer.notify_finished`).
SPEECH_FINISHED_SECONDS: float = 1.0


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


class SpeechBuffer(IndexedBuffer):
	"""Indexed capture of NVDA speech sequences with wait-for / wait-to-finish.

	``exact_finish`` selects how "speech has finished" is decided, and is set by
	whichever speech source the AdapterFactory built: silent mode sets it true
	and drives :meth:`notify_finished` from the spy synth's
	``synthDoneSpeaking``; live mode leaves it false and falls back to the
	elapsed-time heuristic.
	"""

	def __init__(self, clock: Clock, *, exact_finish: bool = False) -> None:
		super().__init__(clock)
		self.exact_finish: bool = exact_finish
		self._speaking: bool = False
		self._observer: Callable[[str], None] | None = None

	def _sentinel(self) -> Any:
		return [""]

	def _render(self, entry: Any) -> str:
		return _join_speech(entry)

	def set_observer(self, observer: Callable[[str], None] | None) -> None:
		"""Register a callback fired (outside the lock) for each appended text.

		The Session wires this to the Transcript port so captured speech is
		logged bridge-side even if the agent never fetches it.
		"""
		self._observer = observer

	def append(self, sequence: Any) -> None:
		"""Record a captured speech sequence; called from NVDA's speech thread."""
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
