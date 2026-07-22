# nvdaMcpBridge adapters -- FileTranscript: the Transcript vocabulary.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# ROLE: adapter. IMPLEMENTS the Transcript domain port.
# DEPENDS ON: the FileWriter adapter seam -- never on ``open()`` directly, which
#             is what makes this precisely testable: its test asserts the exact
#             lines produced, with a fake writer and no filesystem.
# USED BY: the Session controller, through the port.
# BUILT BY: create_session_log (below) / wiring.
#
# Everything here is a formatting decision: one timestamped line per event, so a
# tester can reconstruct a silent run -- gestures interleaved with the speech
# they produced, plus session open/close. The IO lives one layer down, in the
# leaf.

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from ..domain.ports.transcript import Transcript
from .text_file_writer import TextFileWriter

if TYPE_CHECKING:
	from .ports.file_writer import FileWriter

#: Default number of recent session logs to retain; older ones are pruned.
DEFAULT_KEEP: int = 20


def _wallclock() -> str:
	return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


class FileTranscript(Transcript):
	"""Turns session events into timestamped transcript lines.

	Timestamps come from an injectable callable (defaulting to wall-clock) so
	tests get deterministic output.
	"""

	def __init__(self, writer: FileWriter, *, timestamp: Callable[[], str] = _wallclock) -> None:
		self._writer = writer
		self._timestamp = timestamp
		self._open = False

	@property
	def path(self) -> str:
		return self._writer.path

	def open(self) -> None:
		self._writer.open()
		self._open = True

	def _line(self, text: str) -> None:
		# Events outside an open session are dropped rather than buffered: there
		# is no session for a reader to attach them to.
		if not self._open:
			return
		self._writer.write_line(f"{self._timestamp()} {text}")

	def session_opened(self, mode: str, synth: str) -> None:
		self._line(f"SESSION OPEN mode={mode} synth={synth}")

	def gesture(self, gesture_id: str) -> None:
		self._line(f"GESTURE {gesture_id}")

	def speech(self, text: str) -> None:
		self._line(f"SPEECH {text!r}")

	def note(self, text: str) -> None:
		self._line(f"NOTE {text}")

	def session_closed(self, reason: str) -> None:
		self._line(f"SESSION CLOSE reason={reason}")
		self._open = False
		self._writer.close()


def create_session_log(
	logs_dir: str | os.PathLike[str],
	*,
	keep: int = DEFAULT_KEEP,
	timestamp: Callable[[], str] = _wallclock,
	name_stamp: Callable[[], str] | None = None,
) -> FileTranscript:
	"""Compose a transcript over a fresh ``session-<stamp>.log``, pruning old ones.

	The one place that picks the concrete TextFileWriter for a real session.
	``name_stamp`` builds the filename component (defaults to a filesystem-safe
	wall-clock stamp); ``keep`` bounds how many ``session-*.log`` files survive,
	oldest deleted first.
	"""
	directory = Path(logs_dir)
	directory.mkdir(parents=True, exist_ok=True)
	stamp = (name_stamp or (lambda: datetime.now().strftime("%Y%m%d-%H%M%S-%f")))()
	transcript = FileTranscript(TextFileWriter(directory / f"session-{stamp}.log"), timestamp=timestamp)
	transcript.open()
	_prune(directory, keep)
	return transcript


def _prune(directory: Path, keep: int) -> None:
	# Names embed a time-sortable stamp, so a lexical sort is a chronological
	# one -- and, unlike mtime, is stable when files land in the same millisecond.
	existing = sorted(directory.glob("session-*.log"), key=lambda p: p.name)
	for stale in existing[: max(0, len(existing) - keep)]:
		try:
			stale.unlink()
		except OSError:
			pass
