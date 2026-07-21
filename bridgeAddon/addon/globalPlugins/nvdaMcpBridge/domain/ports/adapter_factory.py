# nvdaMcpBridge domain -- the AdapterFactory port + the AdapterSet it returns.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# ROLE: domain port. Builds the mode-specific collaborators, once, after hello.
# USED BY: the Session controller.
# IMPLEMENTED BY: adapters/nvda_adapter_factory.py in session C (chooses the
#                 silent vs live speech source, plus the braille source and
#                 gesture sender); tests/fakes/adapter_factory.py. There is no
#                 synth swapper: silent mode suppresses NVDA's speak() output and
#                 leaves the real synth loaded (see nvda_silent_speech_source),
#                 so the synth is never swapped.
#
# Why a factory at all: the capture mode is only known once the client's ``hello``
# arrives (AGENTS.md, Decided -- no configure-after-construction). So wiring.py
# injects this factory rather than a fixed adapter set, and the Session calls
# ``build(mode)`` exactly once, after a successful handshake. AdapterSet is this
# port's own DTO, so it lives in this file.

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from ... import protocol
from .braille_source import BrailleSource
from .gesture_sender import GestureSender
from .speech_source import SpeechSource


@dataclass(frozen=True)
class AdapterSet:
	"""The mode-specific collaborators the Session drives during a session."""

	speech_source: SpeechSource
	braille_source: BrailleSource
	gesture_sender: GestureSender


class AdapterFactory(ABC):
	"""Builds the :class:`AdapterSet` for a capture mode, known only after hello."""

	@abstractmethod
	def build(self, mode: protocol.CaptureMode) -> AdapterSet:
		"""Construct the collaborators for ``mode``."""
