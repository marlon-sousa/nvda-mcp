# nvdaMcpBridge domain -- PingHandler: liveness probe.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# ROLE: command handler for `ping`. Proves the peer is alive (which resets the
# heartbeat, in the Session) but NOT that the agent is still testing -- so it
# deliberately does not reset the command-inactivity watchdog.

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .... import protocol
from .command_handler import CommandHandler

if TYPE_CHECKING:
	from .session_context import SessionContext


class PingHandler(CommandHandler):
	resets_inactivity = False

	def execute(self, ctx: SessionContext, request: protocol.Request) -> Any:
		return protocol.AckResult()
