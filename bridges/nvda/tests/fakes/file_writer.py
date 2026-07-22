# nvdaMcpBridge tests -- FakeFileWriter, standing in for the FileWriter seam.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# FAKES: adapters/ports/file_writer.py
#
# Records lines in memory, so FileTranscript's test can assert the exact
# vocabulary it produced without a filesystem -- which is the whole point of
# having a FileWriter seam under it.

from __future__ import annotations

from nvdaMcpBridge.adapters.ports.file_writer import FileWriter


class FakeFileWriter(FileWriter):
	"""An in-memory :class:`FileWriter`."""

	def __init__(self, path: str = "session.log") -> None:
		self._path = path
		self.lines: list[str] = []
		self.opened = False
		self.closed = False

	@property
	def path(self) -> str:
		return self._path

	def open(self) -> None:
		self.opened = True

	def write_line(self, text: str) -> None:
		self.lines.append(text)

	def close(self) -> None:
		self.closed = True
