# nvdaMcpBridge tests -- FakeAdapterFactory, standing in for the AdapterFactory port.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# FAKES: domain/ports/adapter_factory.py
#
# Assembles the fake NVDA from the individual fakes and hands the SAME instances
# to both the Session (via the AdapterSet it returns) and the test (via its
# attributes), so a test can, e.g., assert the swapper's call order or make a
# gesture speak. It also records the mode it was asked to build for -- the check
# that the Session deferred construction until hello and passed the right mode.
#
# The gesture sender is wired to the speech source here, at construction, exactly
# as the real factory will bind the spy synth to the buffer -- that link is what
# lets a scripted gesture's speech reach the session's buffer.

from __future__ import annotations

from typing import TYPE_CHECKING, Mapping, Sequence

from nvdaMcpBridge.domain.ports.adapter_factory import AdapterFactory, AdapterSet

from .braille_source import FakeBrailleSource
from .gesture_sender import FakeGestureSender
from .speech_source import FakeSpeechSource

if TYPE_CHECKING:
	from nvdaMcpBridge import protocol


class FakeAdapterFactory(AdapterFactory):
	"""Builds a fake AdapterSet and remembers the mode it was built for."""

	def __init__(
		self,
		*,
		reject: Sequence[str] | None = None,
		speech: Mapping[str, Sequence[str]] | None = None,
	) -> None:
		self.speech_source = FakeSpeechSource()
		self.braille_source = FakeBrailleSource()
		self.gesture_sender = FakeGestureSender(self.speech_source, reject=reject, speech=speech)
		self.built_mode: protocol.CaptureMode | None = None

	def build(self, mode: protocol.CaptureMode) -> AdapterSet:
		self.built_mode = mode
		return AdapterSet(
			speech_source=self.speech_source,
			braille_source=self.braille_source,
			gesture_sender=self.gesture_sender,
		)
