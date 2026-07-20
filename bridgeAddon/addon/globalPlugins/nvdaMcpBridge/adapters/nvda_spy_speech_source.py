# nvdaMcpBridge adapters -- NvdaSpySpeechSource: silent-mode speech capture.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# ROLE: adapter. IMPLEMENTS the SpeechSource port for SILENT mode -- capture via
#       the spy synth, so NVDA makes no sound.
# BUILT BY: adapters/nvda_adapter_factory.py when hello asks for silent mode.
# COLLABORATORS: spy_sink (registers the sink the spy synth's speak() feeds) and
#                synthDriverHandler.synthDoneSpeaking (the exact "speech finished"
#                signal silent mode uses instead of the elapsed-time heuristic).
#
# On pyright's ignore list (imports NVDA); the capture logic worth testing lives
# in the pure spy_sink and the SpeechBuffer, both strict-checked and unit-tested.
# Validated live by the 9c checklist.
#
# NVDA holds extension-point handlers by WEAK reference, so this instance must
# outlive the registration -- it does: the AdapterSet keeps it for the session,
# and stop() unregisters explicitly at teardown.

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Sequence

import synthDriverHandler

from ..domain.ports.speech_source import SpeechSource
from . import spy_sink

if TYPE_CHECKING:
	from ..domain.entities.speech_buffer import SpeechBuffer


class NvdaSpySpeechSource(SpeechSource):
	"""Feeds the SpeechBuffer from the spy synth (silent mode)."""

	def __init__(self) -> None:
		self._buffer: SpeechBuffer | None = None
		self._registered = False

	def start(self, buffer: SpeechBuffer) -> None:
		self._buffer = buffer
		spy_sink.set_sink(self._on_speech)
		synthDriverHandler.synthDoneSpeaking.register(self._on_done)
		self._registered = True

	def stop(self) -> None:
		spy_sink.clear_sink()
		if self._registered:
			synthDriverHandler.synthDoneSpeaking.unregister(self._on_done)
			self._registered = False
		self._buffer = None

	def _on_speech(self, text_chunks: Sequence[str]) -> None:
		buffer = self._buffer
		if buffer is not None:
			buffer.append(list(text_chunks))

	def _on_done(self, synth: Any = None, **kwargs: Any) -> None:
		# Filtered to our spy: other synths' done-speaking is not our concern.
		if synth is not None and getattr(synth, "name", None) == spy_sink.SPY_SYNTH_NAME:
			buffer = self._buffer
			if buffer is not None:
				buffer.notify_finished()
