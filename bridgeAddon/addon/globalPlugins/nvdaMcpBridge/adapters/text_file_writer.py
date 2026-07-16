# nvdaMcpBridge adapters -- TextFileWriter: the FileWriter leaf.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# ROLE: LEAF adapter. IMPLEMENTS the FileWriter seam by doing the real file IO.
# USED BY: adapters/file_transcript.py, via the seam, never directly.
# BUILT BY: wiring / create_session_log.
#
# Deliberately the dumbest file in the addon: it makes no decisions, so there is
# nothing here a unit test could assert that ``open()`` does not already
# guarantee -- which is why it has no test file. Everything worth testing lives
# above it in FileTranscript, exercised against a fake writer. Keep it that way:
# if you are tempted to add a decision here, it belongs upstairs.
#
# Note we do NOT reuse NVDA's logHandler for this. That writes to NVDA's single
# global log, gated by the user's configured level, whereas a transcript is a
# private per-session file a tester reads after a silent run. NVDA's log is the
# right sink for diagnostics -- an edge concern (plugin.py), not this.

from __future__ import annotations

import os
from pathlib import Path
from typing import TextIO

from .ports.file_writer import FileWriter


class TextFileWriter(FileWriter):
	"""UTF-8, line-buffered file sink."""

	def __init__(self, path: str | os.PathLike[str]) -> None:
		self._path = Path(path)
		self._file: TextIO | None = None

	@property
	def path(self) -> str:
		return str(self._path)

	def open(self) -> None:
		self._path.parent.mkdir(parents=True, exist_ok=True)
		# buffering=1 is line buffering: a crash cannot lose the tail.
		self._file = open(self._path, "w", encoding="utf-8", buffering=1)

	def write_line(self, text: str) -> None:
		if self._file is None:
			return
		try:
			self._file.write(text + "\n")
			self._file.flush()
		except OSError:
			pass  # a failed transcript write must never take a session down

	def close(self) -> None:
		f = self._file
		self._file = None
		if f is not None:
			try:
				f.close()
			except OSError:
				pass
