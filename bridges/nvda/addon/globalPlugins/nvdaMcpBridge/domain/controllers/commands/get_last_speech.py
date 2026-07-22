# nvdaMcpBridge domain -- GetLastSpeechHandler: the most recent speech sequence.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# ROLE: command handler for `getLastSpeech`.

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .... import protocol
from .command_handler import CommandHandler

if TYPE_CHECKING:
	from .session_context import SessionContext


class GetLastSpeechHandler(CommandHandler):
	def execute(self, ctx: SessionContext, request: protocol.Request) -> Any:
		text, index = ctx.speech_buffer.get_last()
		return protocol.LastSpeechResult(text=text, index=index)
