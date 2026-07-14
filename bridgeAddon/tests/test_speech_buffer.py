# Tests for the indexed speech/braille buffers. Copyright (C) 2026 Marlon
# Brandao de Sousa. GPL-2. See COPYING.txt.

from __future__ import annotations

from fakes import FakeClock

from nvdaMcpBridge.speech_buffer import SPEECH_FINISHED_SECONDS, BrailleBuffer, SpeechBuffer


def _speech(clock: FakeClock, *, exact: bool = False) -> SpeechBuffer:
	return SpeechBuffer(clock, exact_finish=exact)


# -- index bookkeeping --------------------------------------------------------


def test_empty_buffer_starts_at_sentinel_index_zero() -> None:
	buf = _speech(FakeClock())
	assert buf.last_index() == 0
	assert buf.next_index() == 1
	# The sentinel renders empty, so last speech is "".
	assert buf.get_last() == ("", 0)


def test_append_advances_indices_and_next_index_is_the_bookmark() -> None:
	buf = _speech(FakeClock())
	bookmark = buf.next_index()
	buf.append(["hello ", "world"])
	assert bookmark == 1
	assert buf.last_index() == 1
	assert buf.next_index() == 2
	assert buf.get_last() == ("hello world", 1)


def test_get_since_returns_half_open_range_and_joins_nonempty() -> None:
	buf = _speech(FakeClock())
	start = buf.next_index()
	buf.append(["one"])
	buf.append([""])  # empty sequence is skipped in the joined text
	buf.append(["two"])
	text, from_index, to_index = buf.get_since(start)
	assert text == "one\ntwo"
	assert (from_index, to_index) == (1, 4)


def test_get_since_clamps_stale_or_negative_bookmark() -> None:
	buf = _speech(FakeClock())
	buf.append(["a"])
	# Negative and past-the-end indices must not raise.
	assert buf.get_since(-5)[1] == 0
	assert buf.get_since(999) == ("", 999, 2)


def test_speech_sequences_keep_only_string_parts() -> None:
	buf = _speech(FakeClock())
	# Non-string speech commands (here stand-ins) are dropped.
	buf.append(["say ", object(), "this", 42])
	assert buf.get_last()[0] == "say this"


# -- search / wait ------------------------------------------------------------


def test_index_of_respects_exclusive_after_index() -> None:
	buf = _speech(FakeClock())
	buf.append(["alpha"])  # index 1
	buf.append(["beta"])  # index 2
	buf.append(["alpha again"])  # index 3
	assert buf.index_of("alpha") == 1
	assert buf.index_of("alpha", after_index=1) == 3
	assert buf.index_of("missing") == -1


def test_wait_for_returns_immediately_when_already_present() -> None:
	clock = FakeClock()
	buf = _speech(clock)
	buf.append(["found it"])
	found, index, text = buf.wait_for("found", after_index=None, timeout=5.0)
	assert (found, index, text) == (True, 1, "found it")
	assert clock.sleeps == []  # never had to wait


def test_wait_for_times_out_without_real_sleep() -> None:
	clock = FakeClock()
	buf = _speech(clock)
	found, index, text = buf.wait_for("never", after_index=None, timeout=5.0)
	assert found is False
	assert index == buf.next_index()
	assert text == ""
	# The fake clock advanced past the deadline via instant sleeps.
	assert clock.monotonic() >= 5.0


# -- finish semantics ---------------------------------------------------------


def test_live_mode_finish_uses_elapsed_heuristic() -> None:
	clock = FakeClock()
	buf = _speech(clock, exact=False)
	buf.append(["talking"])
	# Immediately after speech it is not finished...
	assert buf._has_finished() is False  # type: ignore[attr-defined]
	clock.advance(SPEECH_FINISHED_SECONDS + 0.01)
	assert buf._has_finished() is True  # type: ignore[attr-defined]


def test_live_mode_wait_to_finish_true_after_quiet_period() -> None:
	clock = FakeClock()
	buf = _speech(clock, exact=False)
	buf.append(["talking"])
	assert buf.wait_to_finish(timeout=5.0) is True


def test_silent_mode_finish_waits_for_synth_done_signal() -> None:
	clock = FakeClock()
	buf = _speech(clock, exact=True)
	buf.append(["talking"])
	# Elapsed time is irrelevant in exact mode; only the done signal finishes.
	clock.advance(60.0)
	assert buf.wait_to_finish(timeout=0.0) is False
	buf.notify_finished()
	assert buf.wait_to_finish(timeout=0.0) is True


def test_observer_fires_for_nonempty_appends_only() -> None:
	buf = _speech(FakeClock())
	seen: list[str] = []
	buf.set_observer(seen.append)
	buf.append(["spoken"])
	buf.append([""])  # empty -> no observer call
	assert seen == ["spoken"]


# -- braille ------------------------------------------------------------------


def test_braille_dedups_consecutive_and_ignores_empty() -> None:
	buf = BrailleBuffer(FakeClock())
	buf.append("line one")
	buf.append("line one")  # duplicate refresh -> dropped
	buf.append("   ")  # whitespace only -> dropped
	buf.append("line two")
	text, from_index, to_index = buf.get_since(1)
	assert text == "line one\nline two"
	assert (from_index, to_index) == (1, 3)
