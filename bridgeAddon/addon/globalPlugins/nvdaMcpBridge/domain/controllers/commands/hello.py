# nvdaMcpBridge domain -- HelloHandler: the bootstrap command.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# ROLE: command handler for `hello` -- the one command valid before the handshake
# completes, and the one that BUILDS the session. Unlike the operational handlers
# (which only read a ready SessionContext), hello is wired with the AdapterFactory
# and the NVDA version, and it populates the context: builds the mode-specific
# adapters, creates the buffers, and starts capture. There is NO synth swap: the
# reader's real synth stays loaded in every mode; silent mode suppresses NVDA's
# speak() output at the speech source instead (see nvda_silent_speech_source), so
# NVDA and other add-ons keep seeing their configured synth as valid and active.
#
# On a protocol-version mismatch it raises CommandError before touching anything
# -- the factory is never called -- and the Session ends the handshake.

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .... import protocol
from ...entities.braille_buffer import BrailleBuffer
from ...entities.speech_buffer import SpeechBuffer
from .command_handler import CommandError, CommandHandler

if TYPE_CHECKING:
	from ....protocol import Capability, ReaderInfo
	from ...ports.adapter_factory import AdapterFactory
	from .session_context import SessionContext


class HelloHandler(CommandHandler):
	available_before_hello = True

	def __init__(
		self,
		factory: AdapterFactory,
		reader: ReaderInfo,
		capabilities: list[Capability],
	) -> None:
		self._factory = factory
		self._reader = reader
		self._capabilities = capabilities

	def execute(self, ctx: SessionContext, request: protocol.Request) -> Any:
		params = protocol.from_dict(protocol.HelloParams, request.params)
		if params.protocolVersion != protocol.PROTOCOL_VERSION:
			raise CommandError(
				f"protocol version mismatch: bridge speaks {protocol.PROTOCOL_VERSION}, "
				f"client sent {params.protocolVersion}"
			)
		ctx.transcript.open()
		# Capture is always on (spec 0009); logLevel, if set, additionally bumps
		# NVDA's own verbosity for the session -- restored at teardown.
		ctx.log_capture.start(params.logLevel)
		adapters = self._factory.build(params.mode)
		# Installed before starting capture, so teardown can stop the sources even
		# if a start() below raises.
		ctx.adapters = adapters

		# No exact-finish signal: silent mode suppresses at the speak() filter, so
		# there is no synth "done speaking" to key off; both modes use the buffer's
		# elapsed-time heuristic.
		speech = SpeechBuffer(ctx.clock, exact_finish=False)
		braille = BrailleBuffer(ctx.clock)
		speech.set_observer(ctx.transcript.speech)
		ctx.speech = speech
		ctx.braille = braille
		adapters.speech_source.start(speech)
		adapters.braille_source.start(braille)

		# The reader's real synth stays loaded in every mode; just report it.
		synth = ctx.announcer.current_synth()
		ctx.transcript.session_opened(params.mode, synth)

		return protocol.HelloResult(
			protocolVersion=protocol.PROTOCOL_VERSION,
			reader=self._reader,
			capabilities=self._capabilities,
			mode=params.mode,
			synth=synth,
			logPath=ctx.transcript.path,
			nvdaLogPath=ctx.log_capture.path,
		)
