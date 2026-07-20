# nvdaMcpBridge adapters -- NvdaLiveSpeechSource: live-mode speech capture.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# ROLE: adapter. IMPLEMENTS the SpeechSource port for LIVE mode -- the real synth
#       keeps talking while we observe what it was asked to say.
# BUILT BY: adapters/nvda_adapter_factory.py when hello asks for live mode.
# COLLABORATORS: speech.extensions.pre_speechQueued -- the fully processed
#                sequence about to be synthesised (the pattern NVDA's own
#                _remoteClient uses). Live mode has no exact finish signal, so the
#                SpeechBuffer's elapsed-time heuristic decides "finished".
#
# On pyright's ignore list (imports NVDA). NVDA holds handlers weakly, so this
# instance must outlive its registration -- the AdapterSet keeps it for the
# session; stop() unregisters at teardown.

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from speech.extensions import pre_speechQueued

from ..domain.ports.speech_source import SpeechSource

if TYPE_CHECKING:
	from ..domain.entities.speech_buffer import SpeechBuffer


class NvdaLiveSpeechSource(SpeechSource):
	"""Feeds the SpeechBuffer from the pre_speechQueued hook (live mode)."""

	def __init__(self) -> None:
		self._buffer: SpeechBuffer | None = None
		self._registered = False

	def start(self, buffer: SpeechBuffer) -> None:
		self._buffer = buffer
		pre_speechQueued.register(self._on_speech_queued)
		self._registered = True

	def stop(self) -> None:
		if self._registered:
			pre_speechQueued.unregister(self._on_speech_queued)
			self._registered = False
		self._buffer = None

	def _on_speech_queued(self, speechSequence: Any = None, **kwargs: Any) -> None:
		buffer = self._buffer
		if buffer is not None and speechSequence:
			buffer.append(speechSequence)
