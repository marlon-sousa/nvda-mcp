# Unit tests for adapters/file_transcript.py.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# FileTranscript owns every decision (the transcript vocabulary), so it is
# tested precisely against a FakeFileWriter: exact lines, no filesystem. Only
# create_session_log -- which picks real paths and prunes real files -- touches
# the disk. The TextFileWriter leaf beneath it has no test file on purpose: it
# makes no decisions. See AGENTS.md ("Testing").

from __future__ import annotations

from pathlib import Path

import pytest
from fakes.file_writer import FakeFileWriter

from nvdaMcpBridge.adapters.file_transcript import FileTranscript, create_session_log


def _fixed_timestamp() -> str:
	return "T"


@pytest.fixture
def writer() -> FakeFileWriter:
	return FakeFileWriter()


@pytest.fixture
def transcript(writer: FakeFileWriter) -> FileTranscript:
	"""A transcript over the same `writer` the test can inspect, by construction."""
	return FileTranscript(writer, timestamp=_fixed_timestamp)


# -- vocabulary (no filesystem) ----------------------------------------------


def test_records_every_event_in_order_with_timestamps(
	transcript: FileTranscript, writer: FakeFileWriter
) -> None:
	transcript.open()
	transcript.session_opened("silent", "espeak")
	transcript.synth_swapped("espeak")
	transcript.gesture("NVDA+f7")
	transcript.speech("Find dialog")
	transcript.note("something odd")
	transcript.synth_restored("espeak")
	transcript.session_closed("client-bye")
	assert writer.lines == [
		"T SESSION OPEN mode=silent synth=espeak",
		"T SYNTH SWAP in=nvdaMcpSpy saved=espeak",
		"T GESTURE NVDA+f7",
		"T SPEECH 'Find dialog'",
		"T NOTE something odd",
		"T SYNTH RESTORE -> espeak",
		"T SESSION CLOSE reason=client-bye",
	]


def test_speech_is_quoted_so_whitespace_survives_reading(
	transcript: FileTranscript, writer: FakeFileWriter
) -> None:
	transcript.open()
	transcript.speech("  padded  ")
	assert writer.lines == ["T SPEECH '  padded  '"]


def test_open_and_close_are_delegated_to_the_writer(
	transcript: FileTranscript, writer: FakeFileWriter
) -> None:
	transcript.open()
	assert writer.opened is True
	transcript.session_closed("client-bye")
	assert writer.closed is True


def test_path_comes_from_the_writer(transcript: FileTranscript, writer: FakeFileWriter) -> None:
	assert transcript.path == writer.path


def test_events_before_open_are_dropped(transcript: FileTranscript, writer: FakeFileWriter) -> None:
	transcript.gesture("NVDA+f7")
	assert writer.lines == []


def test_events_after_close_are_dropped(transcript: FileTranscript, writer: FakeFileWriter) -> None:
	transcript.open()
	transcript.session_closed("client-bye")
	transcript.gesture("NVDA+f7")
	assert writer.lines[-1] == "T SESSION CLOSE reason=client-bye"


# -- session log files (real filesystem) -------------------------------------


def test_create_session_log_writes_a_real_file(tmp_path: Path) -> None:
	log = create_session_log(tmp_path, name_stamp=lambda: "0001", timestamp=_fixed_timestamp)
	log.gesture("NVDA+f7")
	log.session_closed("client-bye")
	written = (tmp_path / "session-0001.log").read_text(encoding="utf-8").splitlines()
	assert written == ["T GESTURE NVDA+f7", "T SESSION CLOSE reason=client-bye"]


def test_create_session_log_reports_the_path_it_opened(tmp_path: Path) -> None:
	log = create_session_log(tmp_path, name_stamp=lambda: "0001")
	# `hello` hands this to the agent, so it must be the real file.
	assert Path(log.path) == tmp_path / "session-0001.log"


def test_create_session_log_prunes_the_oldest_sessions(tmp_path: Path) -> None:
	counter = {"n": 0}

	def _stamp() -> str:
		counter["n"] += 1
		return f"{counter['n']:04d}"

	for _ in range(5):
		create_session_log(tmp_path, keep=3, name_stamp=_stamp).session_closed("client-bye")

	# Only the last 3 of the 5 sessions survive.
	assert sorted(p.name for p in tmp_path.glob("session-*.log")) == [
		"session-0003.log",
		"session-0004.log",
		"session-0005.log",
	]


def test_create_session_log_keeps_unrelated_files(tmp_path: Path) -> None:
	(tmp_path / "notes.txt").write_text("keep me", encoding="utf-8")
	create_session_log(tmp_path, keep=1, name_stamp=lambda: "0001").session_closed("client-bye")
	assert (tmp_path / "notes.txt").exists()
