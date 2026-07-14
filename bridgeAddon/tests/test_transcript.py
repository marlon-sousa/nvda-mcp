# Tests for the file-backed transcript adapter. Copyright (C) 2026 Marlon
# Brandao de Sousa. GPL-2. See COPYING.txt.

from __future__ import annotations

from pathlib import Path

from nvdaMcpBridge.adapters.file_transcript import FileTranscript, create_session_log


def _fixed_timestamp() -> str:
	return "T"


def test_transcript_records_events_in_order_flushed_per_line(tmp_path: Path) -> None:
	log = FileTranscript(tmp_path / "session.log", timestamp=_fixed_timestamp)
	log.open()
	log.session_opened("silent", "espeak")
	log.synth_swapped("espeak")
	log.gesture("NVDA+f7")
	log.speech("Find dialog")
	log.synth_restored("espeak")
	log.session_closed("client-bye")
	lines = (tmp_path / "session.log").read_text(encoding="utf-8").splitlines()
	assert lines == [
		"T SESSION OPEN mode=silent synth=espeak",
		"T SYNTH SWAP in=nvdaMcpSpy saved=espeak",
		"T GESTURE NVDA+f7",
		"T SPEECH 'Find dialog'",
		"T SYNTH RESTORE -> espeak",
		"T SESSION CLOSE reason=client-bye",
	]


def test_writes_before_open_are_silently_ignored(tmp_path: Path) -> None:
	log = FileTranscript(tmp_path / "session.log", timestamp=_fixed_timestamp)
	# No open() -> no file, no crash.
	log.gesture("NVDA+f7")
	assert not (tmp_path / "session.log").exists()


def test_create_session_log_names_file_and_prunes_old_sessions(tmp_path: Path) -> None:
	logs = tmp_path / "logs"
	counter = {"n": 0}

	def _stamp() -> str:
		counter["n"] += 1
		return f"{counter['n']:04d}"

	created: list[str] = []
	for _ in range(5):
		log = create_session_log(logs, keep=3, name_stamp=_stamp)
		created.append(Path(log.path).name)
		log.session_closed("client-bye")

	remaining = sorted(p.name for p in logs.glob("session-*.log"))
	# Only the last 3 of the 5 sessions survive.
	assert created == [
		"session-0001.log",
		"session-0002.log",
		"session-0003.log",
		"session-0004.log",
		"session-0005.log",
	]
	assert remaining == ["session-0003.log", "session-0004.log", "session-0005.log"]
