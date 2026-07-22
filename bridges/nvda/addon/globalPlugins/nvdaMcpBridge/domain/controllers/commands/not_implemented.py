# nvdaMcpBridge domain -- NotImplementedHandler: a v1 command with no port yet.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# ROLE: command handler registered for the introspection commands whose ports
# arrive in session E (`getFocusInfo`, `getState`, `getConfig`, `setConfig`). It
# raises a clean CommandError so a newer server degrades gracefully -- on the
# wire these behave exactly like any command error, rather than an unknown
# command, so the client can tell "not yet" from "never".

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .... import protocol
from .command_handler import CommandError, CommandHandler

if TYPE_CHECKING:
	from .session_context import SessionContext


class NotImplementedHandler(CommandHandler):
	def execute(self, ctx: SessionContext, request: protocol.Request) -> Any:
		raise CommandError(f"{request.cmd} is not implemented in this bridge yet")
