# nvdaMcpBridge domain -- SessionContext: the per-session collaborators a handler sees.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# ROLE: the seam between the Session and its command handlers. A handler is handed
# ONE of these and nothing else, so it can be tested with a hand-built context and
# no Session, no run loop -- which is the whole point of splitting dispatch out.
# DEPENDS ON: the Clock/Transcript ports, the buffer entities, the AdapterSet DTO,
# and TeardownReason -- never NVDA.
# BUILT BY: the Session (once, at session start). Populated by the hello handler,
# which is the bootstrap command that builds the mode-specific state.
#
# Deliberately NARROW. A handler that needs to end the session gets exactly one
# capability -- close(reason) -- not a handle to the Session, so a command can
# never reach into lifecycle internals. The session-scoped entities (speech /
# braille buffers, the AdapterSet) are None until hello installs them; the
# ``*_buffer`` / ``adapters`` accessors assert they are present, so an operational
# handler (only ever dispatched AFTER hello) reads them without a None check.

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
	from ...entities.braille_buffer import BrailleBuffer
	from ...entities.speech_buffer import SpeechBuffer
	from ...ports.adapter_factory import AdapterSet
	from ...ports.announcer import Announcer
	from ...ports.clock import Clock
	from ...ports.transcript import Transcript
	from ..teardown_reason import TeardownReason


class SessionContext:
	"""The per-session collaborators handed to every command handler."""

	def __init__(
		self,
		clock: Clock,
		transcript: Transcript,
		close: Callable[[TeardownReason], None],
		announcer: Announcer,
	) -> None:
		self.clock = clock
		self.transcript = transcript
		self._close = close
		#: The bridge's line to the reader's real synth: read its name (hello) and
		#: speak hints through it (announce), even during silent capture. Always
		#: present -- it never depends on hello.
		self.announcer = announcer
		# Installed by the hello handler; None before it runs.
		self.speech: SpeechBuffer | None = None
		self.braille: BrailleBuffer | None = None
		self.adapters: AdapterSet | None = None

	def close(self, reason: TeardownReason) -> None:
		"""Ask the session to end with ``reason`` (used by bye and the panic path).

		The only lifecycle capability a handler gets. Thread-safe via the Session's
		request_teardown, so bye (session thread) and a panic gesture (another
		thread) share one path.
		"""
		self._close(reason)

	@property
	def speech_buffer(self) -> SpeechBuffer:
		assert self.speech is not None, "speech buffer read before hello installed it"
		return self.speech

	@property
	def braille_buffer(self) -> BrailleBuffer:
		assert self.braille is not None, "braille buffer read before hello installed it"
		return self.braille

	@property
	def adapter_set(self) -> AdapterSet:
		assert self.adapters is not None, "adapters read before hello installed them"
		return self.adapters
