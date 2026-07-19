# nvdaMcpBridge domain -- HelloHandler: the bootstrap command.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# ROLE: command handler for `hello` -- the one command valid before the handshake
# completes, and the one that BUILDS the session. Unlike the operational handlers
# (which only read a ready SessionContext), hello is wired with the AdapterFactory
# and the NVDA version, and it populates the context: builds the mode-specific
# adapters, creates the buffers, starts capture, and (silent mode only) swaps the
# synth. It installs the AdapterSet onto the context as soon as build() succeeds,
# so the Session's teardown can restore the synth even if a later step here fails.
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
		adapters = self._factory.build(params.mode)
		# Installed before starting capture, so teardown can restore even if a
		# start() below raises.
		ctx.adapters = adapters

		silent = params.mode is protocol.CaptureMode.SILENT
		speech = SpeechBuffer(ctx.clock, exact_finish=silent)
		braille = BrailleBuffer(ctx.clock)
		speech.set_observer(ctx.transcript.speech)
		ctx.speech = speech
		ctx.braille = braille
		adapters.speech_source.start(speech)
		adapters.braille_source.start(braille)

		synth = adapters.synth_swapper.current_synth()
		ctx.transcript.session_opened(params.mode, synth)
		if silent:
			real = adapters.synth_swapper.swap_to_spy()
			ctx.swapped_real = real
			ctx.transcript.synth_swapped(real)

		return protocol.HelloResult(
			protocolVersion=protocol.PROTOCOL_VERSION,
			reader=self._reader,
			capabilities=self._capabilities,
			mode=params.mode,
			synth=synth,
			logPath=ctx.transcript.path,
		)
