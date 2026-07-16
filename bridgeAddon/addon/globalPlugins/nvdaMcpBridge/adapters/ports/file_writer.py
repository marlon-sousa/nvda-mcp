# nvdaMcpBridge adapters -- the FileWriter seam.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# ROLE: append lines to a file. An ADAPTER SEAM, not a domain port -- the domain
#       has no idea the transcript is a file at all.
# USED BY: adapters/file_transcript.py, which owns the transcript *vocabulary*
#          and delegates every actual write here.
# IMPLEMENTED BY: adapters/text_file_writer.py (leaf: real open/write/flush);
#                 tests/fakes/file_writer.py FakeFileWriter (records in memory).
#
# This split is what makes the transcript adapter precisely testable: its test
# asserts the exact lines produced without touching a filesystem, and the only
# untestable code left is a leaf that makes no decisions.

from __future__ import annotations

from abc import ABC, abstractmethod


class FileWriter(ABC):
	"""A line-oriented sink, flushed per line."""

	@property
	@abstractmethod
	def path(self) -> str:
		"""Where the lines land."""

	@abstractmethod
	def open(self) -> None: ...

	@abstractmethod
	def write_line(self, text: str) -> None:
		"""Append one line, flushed.

		Per-line flushing is a requirement, not a tuning detail: a crashed
		harness must not lose the tail of the transcript. Best-effort -- a failed
		write must never raise, because a broken log must never take down a
		session (nor block the synth restore).
		"""

	@abstractmethod
	def close(self) -> None: ...
