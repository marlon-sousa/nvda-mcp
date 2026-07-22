# Unit tests for domain/entities/indexed_buffer.py.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# The base's own contract -- index bookkeeping, the half-open range reads and
# the wait loop -- exercised through a minimal concrete subclass, so it is
# tested once here rather than incidentally through whichever subclass happened
# to be handy. SpeechBuffer / BrailleBuffer then test only what they add.

from __future__ import annotations

from typing import Any

import pytest
from fakes.clock import FakeClock

from nvdaMcpBridge.domain.entities.indexed_buffer import IndexedBuffer


class _StubBuffer(IndexedBuffer):
	"""The smallest possible concrete buffer: entries are plain strings."""

	def _sentinel(self) -> Any:
		return ""

	def _render(self, entry: Any) -> str:
		return entry if isinstance(entry, str) else ""

	def append(self, text: str) -> None:
		with self._lock:
			self._entries.append(text)
			self._last_time = self._clock.monotonic()


@pytest.fixture
def buffer(clock: FakeClock) -> _StubBuffer:
	return _StubBuffer(clock)


# -- index bookkeeping --------------------------------------------------------


def test_starts_at_sentinel_index_zero(buffer: _StubBuffer) -> None:
	assert buffer.last_index() == 0
	assert buffer.next_index() == 1
	# The sentinel renders empty, so the last entry reads as "".
	assert buffer.get_last() == ("", 0)


def test_append_advances_indices_and_next_index_is_the_bookmark(buffer: _StubBuffer) -> None:
	bookmark = buffer.next_index()
	buffer.append("one")
	assert bookmark == 1
	assert buffer.last_index() == 1
	assert buffer.next_index() == 2
	assert buffer.get_last() == ("one", 1)


# -- range reads --------------------------------------------------------------


def test_get_since_returns_half_open_range_and_joins_nonempty(buffer: _StubBuffer) -> None:
	start = buffer.next_index()
	buffer.append("one")
	buffer.append("")  # empty entry is skipped in the joined text
	buffer.append("two")
	text, from_index, to_index = buffer.get_since(start)
	assert text == "one\ntwo"
	assert (from_index, to_index) == (1, 4)


def test_get_since_clamps_a_stale_or_negative_bookmark(buffer: _StubBuffer) -> None:
	buffer.append("a")
	# A bookmark from a previous session must not raise.
	assert buffer.get_since(-5)[1] == 0
	assert buffer.get_since(999) == ("", 999, 2)


# -- the wait loop ------------------------------------------------------------


def test_wait_returns_immediately_when_already_true(clock: FakeClock, buffer: _StubBuffer) -> None:
	assert buffer._wait(lambda: True, timeout=5.0) is True  # type: ignore[attr-defined]
	assert clock.sleeps == []  # never had to wait


def test_wait_gives_up_at_the_deadline_without_sleeping_for_real(
	clock: FakeClock, buffer: _StubBuffer
) -> None:
	assert buffer._wait(lambda: False, timeout=5.0) is False  # type: ignore[attr-defined]
	# The fake clock advanced past the deadline via instant sleeps.
	assert clock.monotonic() >= 5.0


def test_wait_evaluates_once_even_with_a_zero_timeout(buffer: _StubBuffer) -> None:
	calls: list[int] = []

	def _predicate() -> bool:
		calls.append(1)
		return True

	assert buffer._wait(_predicate, timeout=0.0) is True  # type: ignore[attr-defined]
	assert len(calls) == 1
