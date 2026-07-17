# nvdaMcpBridge domain -- the SpeechSource port.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# ROLE: domain port. Whatever feeds the speech buffer with what NVDA "said".
# USED BY: the Session controller (starts it at hello, stops it at teardown).
# IMPLEMENTED BY: adapters/nvda_*.py in session C (silent: the spy synth's
#                 post_speech; live: the pre_speechQueued hook);
#                 tests/fakes/speech_source.py FakeSpeechSource.
#
# The Session never knows WHICH capture mechanism is running -- only that it can
# be started against a buffer and stopped. The mode-specific choice is the
# AdapterFactory's, made after hello reveals the mode.

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
	from ..entities.speech_buffer import SpeechBuffer


class SpeechSource(ABC):
	"""Feeds captured speech sequences into a :class:`SpeechBuffer`."""

	@abstractmethod
	def start(self, buffer: SpeechBuffer) -> None:
		"""Begin capturing into ``buffer`` (register the hook / spy synth)."""

	@abstractmethod
	def stop(self) -> None:
		"""Stop capturing. Idempotent and never raises -- teardown calls it in a guard."""
