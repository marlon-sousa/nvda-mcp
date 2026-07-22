# nvdaMcpBridge domain -- IndexedBuffer: shared base for the capture buffers.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# ROLE: entity base -- index bookkeeping + thread safety + the wait loop.
# EXTENDED BY: entities/speech_buffer.py, entities/braille_buffer.py.
# DEPENDS ON: the Clock port (injected), nothing else.
#
# A stdlib-only port of the buffer half of NVDA's own ``NVDASpyLib``
# (``tests/system/libraries/SystemTestSpy/speechSpyGlobalPlugin.py``). Captures
# land in an append-only, index-addressed list guarded by an RLock, because the
# capture callback runs on NVDA's speech thread while the session thread reads.
#
# Index-based access -- "everything since index N", "wait for text after index
# N" -- is what makes assertions race-free: the agent bookmarks an index
# (``getNextSpeechIndex``), sends a gesture, then reads/waits from that bookmark,
# so background chatter that arrived earlier can never be mistaken for the
# response to its action.
#
# Index convention (kept identical to NVDASpyLib): a buffer starts with one
# empty sentinel entry at index 0, so ``[-1]`` is always valid and the first
# real capture lands at index 1. ``next_index()`` is the index the next capture
# will occupy; it is the bookmark an agent takes before an action.

from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
	from ..ports.clock import Clock

#: Poll cadence for the wait loops. Small enough to feel instant, large enough
#: not to spin. A fake clock makes ``sleep`` an instant advance, so tests that
#: exercise these loops never actually pause.
POLL_INTERVAL: float = 0.03


class IndexedBuffer:
	"""Common index bookkeeping for the speech and braille buffers.

	Subclasses supply :meth:`_sentinel` (the empty entry at index 0) and
	:meth:`_render` (entry -> displayable string) and decide what an entry is;
	this base owns the lock, append timing, and the index-range reads.
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
			self._clock.sleep(POLL_INTERVAL)
