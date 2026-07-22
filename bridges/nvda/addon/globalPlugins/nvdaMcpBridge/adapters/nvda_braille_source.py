# nvdaMcpBridge adapters -- NvdaBrailleSource: braille capture (both modes).
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# ROLE: adapter. IMPLEMENTS the BrailleSource port. There is no "silent" braille,
#       so the same capture runs in both modes.
# BUILT BY: adapters/nvda_adapter_factory.py, in either mode.
# COLLABORATORS: braille.pre_writeCells -- notified with the raw text NVDA is
#                about to write to the display (the pattern NVDA's own
#                _remoteClient uses); we append rawText to the BrailleBuffer,
#                which de-duplicates consecutive identical refreshes.
#
# On pyright's ignore list (imports NVDA). NVDA holds handlers weakly, so this
# instance must outlive its registration -- the AdapterSet keeps it for the
# session; stop() unregisters at teardown.

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import braille

from ..domain.ports.braille_source import BrailleSource

if TYPE_CHECKING:
	from ..domain.entities.braille_buffer import BrailleBuffer


class NvdaBrailleSource(BrailleSource):
	"""Feeds the BrailleBuffer from the pre_writeCells hook."""

	def __init__(self) -> None:
		self._buffer: BrailleBuffer | None = None
		self._registered = False

	def start(self, buffer: BrailleBuffer) -> None:
		self._buffer = buffer
		braille.pre_writeCells.register(self._on_write_cells)
		self._registered = True

	def stop(self) -> None:
		if self._registered:
			braille.pre_writeCells.unregister(self._on_write_cells)
			self._registered = False
		self._buffer = None

	def _on_write_cells(
		self,
		cells: Any = None,
		rawText: Any = None,
		currentCellCount: Any = None,
		**kwargs: Any,
	) -> None:
		buffer = self._buffer
		if buffer is not None and rawText:
			buffer.append(rawText)
