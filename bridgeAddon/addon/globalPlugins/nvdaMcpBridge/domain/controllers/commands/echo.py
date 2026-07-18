# nvdaMcpBridge domain -- EchoHandler: diagnostic payload round-trip.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# ROLE: command handler for `echo`. Returns the request's payload unchanged. It
# needs nothing from the SessionContext -- its whole value is proving the full
# wire stack (encode -> frame -> decode -> validate -> dispatch -> re-encode)
# survives an arbitrary payload, which no fake and no speech command can isolate.

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .... import protocol
from .command_handler import CommandHandler

if TYPE_CHECKING:
	from .session_context import SessionContext


class EchoHandler(CommandHandler):
	def execute(self, ctx: SessionContext, request: protocol.Request) -> Any:
		params = protocol.from_dict(protocol.EchoParams, request.params)
		return protocol.EchoResult(payload=params.payload)
