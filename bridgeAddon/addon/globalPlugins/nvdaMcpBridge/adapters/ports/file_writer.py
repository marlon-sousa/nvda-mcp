# nvdaMcpBridge adapters -- the FileWriter seam.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# ROLE: append lines to a file. An ADAPTER SEAM, not a domain port.
# USED BY: adapters/file_transcript.py (which owns the transcript *vocabulary*
#          and delegates every actual write here).
# IMPLEMENTED BY: adapters/text_file_writer.py (leaf: real open/write/flush);
#                 tests/fakes.py FakeFileWriter (records lines in memory).
#
# Splitting this out is what makes the transcript adapter precisely testable:
# FileTranscript's test asserts the exact lines it produced without touching a
# filesystem, and the only untestable code left is the ~15-line leaf.

from __future__ import annotations

from abc import ABC, abstractmethod


class FileWriter(ABC):
	"""A line-oriented sink that is flushed per line.

	Per-line flushing is a requirement, not an optimization detail: a crashed
	harness must not lose the tail of the transcript.
	"""

	@property
	@abstractmethod
	def path(self) -> str:
		"""Where the lines land; surfaced to the agent at ``hello``."""

	@abstractmethod
	def open(self) -> None: ...

	@abstractmethod
	def write_line(self, text: str) -> None:
		"""Append one line. Best-effort: must not raise on an IO failure."""

	@abstractmethod
	def close(self) -> None: ...
