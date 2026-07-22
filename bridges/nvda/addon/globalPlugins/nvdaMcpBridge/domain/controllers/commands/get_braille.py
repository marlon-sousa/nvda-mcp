# nvdaMcpBridge domain -- GetBrailleHandler: braille captured since an index.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# ROLE: command handler for `getBraille`. The braille counterpart of getSpeech.

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .... import protocol
from .command_handler import CommandHandler

if TYPE_CHECKING:
	from .session_context import SessionContext


class GetBrailleHandler(CommandHandler):
	def execute(self, ctx: SessionContext, request: protocol.Request) -> Any:
		params = protocol.from_dict(protocol.GetBrailleParams, request.params)
		text, from_index, to_index = ctx.braille_buffer.get_since(params.sinceIndex)
		return protocol.BrailleResult(text=text, fromIndex=from_index, toIndex=to_index)
