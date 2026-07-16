# Unit tests for domain/entities/braille_buffer.py.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# Only what BrailleBuffer adds on top of IndexedBuffer: recording genuine
# changes rather than refreshes. The base's index bookkeeping is tested in
# test_indexed_buffer.py.

from __future__ import annotations

import pytest
from fakes.clock import FakeClock

from nvdaMcpBridge.domain.entities.braille_buffer import BrailleBuffer


@pytest.fixture
def braille(clock: FakeClock) -> BrailleBuffer:
	return BrailleBuffer(clock)


def test_consecutive_duplicates_are_dropped(braille: BrailleBuffer) -> None:
	# NVDA rewrites the whole window on every update; a refresh is not a change.
	braille.append("line one")
	braille.append("line one")
	assert braille.next_index() == 2


def test_empty_and_whitespace_only_updates_are_ignored(braille: BrailleBuffer) -> None:
	braille.append("")
	braille.append("   ")
	assert braille.next_index() == 1  # nothing recorded


def test_text_is_trimmed(braille: BrailleBuffer) -> None:
	braille.append("  padded  ")
	assert braille.get_last() == ("padded", 1)


def test_a_repeat_after_a_change_is_recorded(braille: BrailleBuffer) -> None:
	# Only *consecutive* duplicates collapse; returning to earlier text is a
	# genuine change.
	braille.append("one")
	braille.append("two")
	braille.append("one")
	text, _from_index, _to_index = braille.get_since(1)
	assert text == "one\ntwo\none"


def test_changes_read_back_in_order(braille: BrailleBuffer) -> None:
	braille.append("line one")
	braille.append("line one")  # duplicate refresh -> dropped
	braille.append("   ")  # whitespace only -> dropped
	braille.append("line two")
	text, from_index, to_index = braille.get_since(1)
	assert text == "line one\nline two"
	assert (from_index, to_index) == (1, 3)
