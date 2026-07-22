# nvdaMcpBridge tests -- FakeBrailleSource, standing in for the BrailleSource port.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# FAKES: domain/ports/braille_source.py
#
# The braille counterpart of FakeSpeechSource: records start/stop and lets a test
# inject braille updates directly into the buffer it was started with.

from __future__ import annotations

from typing import TYPE_CHECKING

from nvdaMcpBridge.domain.ports.braille_source import BrailleSource

if TYPE_CHECKING:
	from nvdaMcpBridge.domain.entities.braille_buffer import BrailleBuffer


class FakeBrailleSource(BrailleSource):
	"""Records start/stop and lets a test inject braille updates."""

	def __init__(self) -> None:
		self.buffer: BrailleBuffer | None = None
		self.started = 0
		self.stopped = 0
		#: Braille already on the display when capture starts; emitted at start().
		#: A test seeds this to exercise getBraille without a live NVDA.
		self.initial: list[str] = []

	def start(self, buffer: BrailleBuffer) -> None:
		self.buffer = buffer
		self.started += 1
		for cells in self.initial:
			buffer.append(cells)

	def stop(self) -> None:
		self.stopped += 1

	def emit(self, cells: str) -> None:
		"""Inject a braille update."""
		assert self.buffer is not None, "emit before the source was started"
		self.buffer.append(cells)
