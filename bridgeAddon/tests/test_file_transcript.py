# Tests for the transcript adapter stack. Copyright (C) 2026 Marlon Brandao de
# Sousa. GPL-2. See COPYING.txt.
#
# FileTranscript owns every decision (the transcript vocabulary), so it is
# tested precisely against a FakeFileWriter -- exact lines, no filesystem. Only
# create_session_log, which picks real paths and prunes real files, touches the
# disk; the TextFileWriter leaf beneath it makes no decisions worth asserting.

from __future__ import annotations

from pathlib import Path

from fakes import FakeFileWriter

from nvdaMcpBridge.adapters.file_transcript import FileTranscript, create_session_log


def _fixed_timestamp() -> str:
	return "T"


def _transcript() -> tuple[FileTranscript, FakeFileWriter]:
	writer = FakeFileWriter()
	return FileTranscript(writer, timestamp=_fixed_timestamp), writer


# -- vocabulary (no filesystem) ----------------------------------------------


def test_records_events_in_order_with_timestamps() -> None:
	log, writer = _transcript()
	log.open()
	log.session_opened("silent", "espeak")
	log.synth_swapped("espeak")
	log.gesture("NVDA+f7")
	log.speech("Find dialog")
	log.note("something odd")
	log.synth_restored("espeak")
	log.session_closed("client-bye")
	assert writer.lines == [
		"T SESSION OPEN mode=silent synth=espeak",
		"T SYNTH SWAP in=nvdaMcpSpy saved=espeak",
		"T GESTURE NVDA+f7",
		"T SPEECH 'Find dialog'",
		"T NOTE something odd",
		"T SYNTH RESTORE -> espeak",
		"T SESSION CLOSE reason=client-bye",
	]


def test_open_and_close_are_delegated_to_the_writer() -> None:
	log, writer = _transcript()
	log.open()
	assert writer.opened is True
	log.session_closed("client-bye")
	assert writer.closed is True


def test_path_comes_from_the_writer() -> None:
	log, writer = _transcript()
	assert log.path == writer.path


def test_events_before_open_are_dropped() -> None:
	log, writer = _transcript()
	log.gesture("NVDA+f7")
	assert writer.lines == []


def test_events_after_close_are_dropped() -> None:
	log, writer = _transcript()
	log.open()
	log.session_closed("client-bye")
	log.gesture("NVDA+f7")
	assert writer.lines[-1] == "T SESSION CLOSE reason=client-bye"


# -- session log files (real filesystem) -------------------------------------


def test_create_session_log_writes_a_real_file(tmp_path: Path) -> None:
	log = create_session_log(tmp_path, name_stamp=lambda: "0001", timestamp=_fixed_timestamp)
	log.gesture("NVDA+f7")
	log.session_closed("client-bye")
	written = (tmp_path / "session-0001.log").read_text(encoding="utf-8").splitlines()
	assert written == ["T GESTURE NVDA+f7", "T SESSION CLOSE reason=client-bye"]


def test_create_session_log_prunes_old_sessions(tmp_path: Path) -> None:
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
