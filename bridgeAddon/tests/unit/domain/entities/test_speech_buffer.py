# Unit tests for domain/entities/speech_buffer.py.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# Only what SpeechBuffer adds on top of IndexedBuffer: rendering a speech
# sequence, the search/wait predicates, the two "speech has finished"
# semantics, and the observer. The base's index bookkeeping is tested in
# test_indexed_buffer.py.
#
# The `clock` fixture (conftest) is the same object these buffers were built
# on, so a test that advances time is advancing the buffer's own clock by
# construction. See AGENTS.md ("Testing").

from __future__ import annotations

import pytest
from fakes.clock import FakeClock

from nvdaMcpBridge.domain.entities.speech_buffer import SPEECH_FINISHED_SECONDS, SpeechBuffer


@pytest.fixture
def speech(clock: FakeClock) -> SpeechBuffer:
	"""A live-mode buffer: "finished" falls back to the elapsed heuristic."""
	return SpeechBuffer(clock)


@pytest.fixture
def silent_speech(clock: FakeClock) -> SpeechBuffer:
	"""A silent-mode buffer: "finished" needs the exact synthDoneSpeaking."""
	return SpeechBuffer(clock, exact_finish=True)


# -- rendering ----------------------------------------------------------------


def test_sequences_keep_only_string_parts(speech: SpeechBuffer) -> None:
	# NVDA interleaves SpeechCommand objects with the spoken strings (stand-ins
	# here); only the strings are words.
	speech.append(["say ", object(), "this", 42])
	assert speech.get_last() == ("say this", 1)


def test_adjacent_string_parts_join_without_separators(speech: SpeechBuffer) -> None:
	speech.append(["hello ", "world"])
	assert speech.get_last()[0] == "hello world"


# -- search / wait ------------------------------------------------------------


def test_index_of_respects_exclusive_after_index(speech: SpeechBuffer) -> None:
	speech.append(["alpha"])  # index 1
	speech.append(["beta"])  # index 2
	speech.append(["alpha again"])  # index 3
	assert speech.index_of("alpha") == 1
	assert speech.index_of("alpha", after_index=1) == 3
	assert speech.index_of("missing") == -1


def test_wait_for_returns_immediately_when_already_present(clock: FakeClock, speech: SpeechBuffer) -> None:
	speech.append(["found it"])
	assert speech.wait_for("found", after_index=None, timeout=5.0) == (True, 1, "found it")
	assert clock.sleeps == []  # never had to wait


def test_wait_for_times_out_and_hands_back_a_fresh_bookmark(speech: SpeechBuffer) -> None:
	found, index, text = speech.wait_for("never", after_index=None, timeout=5.0)
	assert found is False
	assert index == speech.next_index()
	assert text == ""


# -- finish semantics ---------------------------------------------------------


def test_live_mode_finish_uses_the_elapsed_heuristic(clock: FakeClock, speech: SpeechBuffer) -> None:
	speech.append(["talking"])
	# Immediately after speech it is not finished...
	assert speech._has_finished() is False  # type: ignore[attr-defined]
	clock.advance(SPEECH_FINISHED_SECONDS + 0.01)
	assert speech._has_finished() is True  # type: ignore[attr-defined]


def test_live_mode_wait_to_finish_true_after_a_quiet_period(speech: SpeechBuffer) -> None:
	speech.append(["talking"])
	assert speech.wait_to_finish(timeout=5.0) is True


def test_silent_mode_finish_waits_for_the_synth_done_signal(
	clock: FakeClock, silent_speech: SpeechBuffer
) -> None:
	silent_speech.append(["talking"])
	# Elapsed time is irrelevant in exact mode; only the done signal finishes.
	clock.advance(60.0)
	assert silent_speech.wait_to_finish(timeout=0.0) is False
	silent_speech.notify_finished()
	assert silent_speech.wait_to_finish(timeout=0.0) is True


# -- observer -----------------------------------------------------------------


def test_observer_fires_for_nonempty_appends_only(speech: SpeechBuffer) -> None:
	seen: list[str] = []
	speech.set_observer(seen.append)
	speech.append(["spoken"])
	speech.append([""])  # empty -> no observer call
	assert seen == ["spoken"]


def test_observer_can_be_unregistered(speech: SpeechBuffer) -> None:
	seen: list[str] = []
	speech.set_observer(seen.append)
	speech.append(["during"])
	speech.set_observer(None)
	speech.append(["after"])
	assert seen == ["during"]
