# nvdaMcpBridge adapters -- NvdaSilentSpeechSource: silent-mode capture + suppress.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# ROLE: adapter. IMPLEMENTS the SpeechSource port for SILENT mode. On pyright's
#       ignore list (imports NVDA); validated by the 9c live-NVDA checklist.
# BUILT BY: adapters/nvda_adapter_factory.py when hello asks for silent mode.
# COLLABORATORS: speech.extensions.filter_speechSequence -- a FILTER NVDA applies
#                to every speech sequence inside speak(), BEFORE it reaches the
#                synth (speech/speech.py:1096; if the filter returns an empty
#                sequence, speak() returns and nothing is synthesized).
#
# THE DESIGN (agreed with Marlon, replacing the old spy-synth swap): we do NOT
# touch the synth at all. NVDA's real synth (espeak/ibmeci/...) stays loaded and
# active, so NVDA and every other add-on keep seeing their configured synth as
# valid -- fully transparent. We register a filter that CAPTURES each sequence
# into the buffer and then returns it EMPTIED, so no audio is produced. "Restore"
# is just stop() unregistering the filter -- speech flows again instantly, with no
# synth reload that could fail. And because NVDA holds filter handlers by WEAK
# reference, if this addon ever dies the suppression lifts on its own: the tester
# can never be stranded mute. If our handler raises, NVDA keeps the original
# sequence (extensionPoints.Filter.apply swallows handler errors), so a bug here
# fails safe toward speech, not silence.
#
# NVDA holds the handler weakly, so this instance must outlive the registration --
# the AdapterSet keeps it for the session; stop() unregisters at teardown.

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from speech.extensions import filter_speechSequence

from ..domain.ports.speech_source import SpeechSource

if TYPE_CHECKING:
	from ..domain.entities.speech_buffer import SpeechBuffer


class NvdaSilentSpeechSource(SpeechSource):
	"""Captures NVDA speech and suppresses it, leaving the real synth loaded."""

	def __init__(self) -> None:
		self._buffer: SpeechBuffer | None = None
		self._registered = False

	def start(self, buffer: SpeechBuffer) -> None:
		self._buffer = buffer
		filter_speechSequence.register(self._capture_and_suppress)
		self._registered = True

	def stop(self) -> None:
		if self._registered:
			filter_speechSequence.unregister(self._capture_and_suppress)
			self._registered = False
		self._buffer = None

	def _capture_and_suppress(self, speechSequence: Any) -> Any:
		# Runs on NVDA's main thread (inside speak()). Capture the words, then
		# return an empty sequence so speak() stops before the synth.
		buffer = self._buffer
		if buffer is not None and speechSequence:
			buffer.append(speechSequence)
		return []
