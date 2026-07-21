# nvdaMcpBridge adapters -- NvdaAdapterFactory: builds the real AdapterSet.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# ROLE: adapter. IMPLEMENTS the AdapterFactory port -- the one place that picks
#       the mode-specific speech source and assembles the NVDA-backed collaborators.
# BUILT BY: wiring.build_session (via the hello handler) in production (9c).
# USED BY: the hello handler, which calls build(mode) once the client reveals it.
#
# On pyright's ignore list only because it imports the nvda_*.py adapters (which
# import NVDA); it makes no NVDA calls itself. The mode branch is the whole point
# of the factory: silent mode captures via the speak() FILTER and suppresses the
# audio while leaving the real synth loaded (NvdaSilentSpeechSource); live mode
# observes the pre_speechQueued hook and lets the real synth talk. Neither mode
# swaps the synth -- there is no synth swapper. Braille and the gesture sender are
# mode-independent.

from __future__ import annotations

from .. import protocol
from ..domain.ports.adapter_factory import AdapterFactory, AdapterSet
from .nvda_braille_source import NvdaBrailleSource
from .nvda_gesture_sender import NvdaGestureSender
from .nvda_live_speech_source import NvdaLiveSpeechSource
from .nvda_silent_speech_source import NvdaSilentSpeechSource


class NvdaAdapterFactory(AdapterFactory):
	"""Assembles the real NVDA-backed AdapterSet for the negotiated capture mode."""

	def build(self, mode: protocol.CaptureMode) -> AdapterSet:
		silent = mode is protocol.CaptureMode.SILENT
		speech_source = NvdaSilentSpeechSource() if silent else NvdaLiveSpeechSource()
		return AdapterSet(
			speech_source=speech_source,
			braille_source=NvdaBrailleSource(),
			gesture_sender=NvdaGestureSender(),
		)
