# Tests for the indexed speech/braille buffers. Copyright (C) 2026 Marlon
# Brandao de Sousa. GPL-2. See COPYING.txt.
#
# The buffers are uniform to construct -- every test wants "a buffer on the
# fake clock" -- so they come from fixtures. The `clock` fixture (conftest) is
# the same object the buffer was built on, so a test that advances time is
# advancing the buffer's own clock by construction. See AGENTS.md ("Testing").

from __future__ import annotations

import pytest
from fakes import FakeClock

from nvdaMcpBridge.domain.entities.braille_buffer import BrailleBuffer
from nvdaMcpBridge.domain.entities.speech_buffer import SPEECH_FINISHED_SECONDS, SpeechBuffer


@pytest.fixture
def speech(clock: FakeClock) -> SpeechBuffer:
	"""A live-mode speech buffer: "finished" falls back to the elapsed heuristic."""
	return SpeechBuffer(clock)


@pytest.fixture
def silent_speech(clock: FakeClock) -> SpeechBuffer:
	"""A silent-mode speech buffer: "finished" needs the exact synthDoneSpeaking."""
	return SpeechBuffer(clock, exact_finish=True)


@pytest.fixture
def braille(clock: FakeClock) -> BrailleBuffer:
	return BrailleBuffer(clock)


# -- index bookkeeping --------------------------------------------------------


def test_empty_buffer_starts_at_sentinel_index_zero(speech: SpeechBuffer) -> None:
	assert speech.last_index() == 0
	assert speech.next_index() == 1
	# The sentinel renders empty, so last speech is "".
	assert speech.get_last() == ("", 0)


def test_append_advances_indices_and_next_index_is_the_bookmark(speech: SpeechBuffer) -> None:
	bookmark = speech.next_index()
	speech.append(["hello ", "world"])
	assert bookmark == 1
	assert speech.last_index() == 1
	assert speech.next_index() == 2
	assert speech.get_last() == ("hello world", 1)


def test_get_since_returns_half_open_range_and_joins_nonempty(speech: SpeechBuffer) -> None:
	start = speech.next_index()
	speech.append(["one"])
	speech.append([""])  # empty sequence is skipped in the joined text
	speech.append(["two"])
	text, from_index, to_index = speech.get_since(start)
	assert text == "one\ntwo"
	assert (from_index, to_index) == (1, 4)


def test_get_since_clamps_stale_or_negative_bookmark(speech: SpeechBuffer) -> None:
	speech.append(["a"])
	# Negative and past-the-end indices must not raise.
	assert speech.get_since(-5)[1] == 0
	assert speech.get_since(999) == ("", 999, 2)


def test_speech_sequences_keep_only_string_parts(speech: SpeechBuffer) -> None:
	# Non-string speech commands (here stand-ins) are dropped.
	speech.append(["say ", object(), "this", 42])
	assert speech.get_last()[0] == "say this"


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
	found, index, text = speech.wait_for("found", after_index=None, timeout=5.0)
	assert (found, index, text) == (True, 1, "found it")
	assert clock.sleeps == []  # never had to wait


def test_wait_for_times_out_without_real_sleep(clock: FakeClock, speech: SpeechBuffer) -> None:
	found, index, text = speech.wait_for("never", after_index=None, timeout=5.0)
	assert found is False
	assert index == speech.next_index()
	assert text == ""
	# The fake clock advanced past the deadline via instant sleeps.
	assert clock.monotonic() >= 5.0


# -- finish semantics ---------------------------------------------------------


def test_live_mode_finish_uses_elapsed_heuristic(clock: FakeClock, speech: SpeechBuffer) -> None:
	speech.append(["talking"])
	# Immediately after speech it is not finished...
	assert speech._has_finished() is False  # type: ignore[attr-defined]
	clock.advance(SPEECH_FINISHED_SECONDS + 0.01)
	assert speech._has_finished() is True  # type: ignore[attr-defined]


def test_live_mode_wait_to_finish_true_after_quiet_period(speech: SpeechBuffer) -> None:
	speech.append(["talking"])
	assert speech.wait_to_finish(timeout=5.0) is True


def test_silent_mode_finish_waits_for_synth_done_signal(
	clock: FakeClock, silent_speech: SpeechBuffer
) -> None:
	silent_speech.append(["talking"])
	# Elapsed time is irrelevant in exact mode; only the done signal finishes.
	clock.advance(60.0)
	assert silent_speech.wait_to_finish(timeout=0.0) is False
	silent_speech.notify_finished()
	assert silent_speech.wait_to_finish(timeout=0.0) is True


def test_observer_fires_for_nonempty_appends_only(speech: SpeechBuffer) -> None:
	seen: list[str] = []
	speech.set_observer(seen.append)
	speech.append(["spoken"])
	speech.append([""])  # empty -> no observer call
	assert seen == ["spoken"]


# -- braille ------------------------------------------------------------------


def test_braille_dedups_consecutive_and_ignores_empty(braille: BrailleBuffer) -> None:
	braille.append("line one")
	braille.append("line one")  # duplicate refresh -> dropped
	braille.append("   ")  # whitespace only -> dropped
	braille.append("line two")
	text, from_index, to_index = braille.get_since(1)
	assert text == "line one\nline two"
	assert (from_index, to_index) == (1, 3)
