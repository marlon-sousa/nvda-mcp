# nvdaMcpBridge domain -- the SpeechSource port.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# ROLE: capture lifecycle -- owns the buffers and the hooks that fill them.
# USED BY: the Session controller (starts/stops it, reads its buffers).
# BUILT BY: the AdapterFactory, already configured for the session's mode.
# IMPLEMENTED BY: adapters/nvda_*.py (spy synth / pre_speechQueued; session C);
#                 tests/fakes.py FakeSpeechSource (test emits speech directly).

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
	from ..entities.braille_buffer import BrailleBuffer
	from ..entities.speech_buffer import SpeechBuffer


class SpeechSource(ABC):
	"""Owns speech/braille capture for a session and the buffers it feeds.

	The concrete source is already built for its mode (silent vs live) by the
	:class:`~.adapter_factory.AdapterFactory`, so :meth:`start` takes no mode: it
	simply registers the NVDA hooks and begins feeding the buffers, and
	:meth:`stop` unregisters (safe to call more than once). The buffers exist for
	the life of the source.
	"""

	@property
	@abstractmethod
	def speech(self) -> SpeechBuffer: ...

	@property
	@abstractmethod
	def braille(self) -> BrailleBuffer: ...

	@abstractmethod
	def start(self) -> None: ...

	@abstractmethod
	def stop(self) -> None: ...
