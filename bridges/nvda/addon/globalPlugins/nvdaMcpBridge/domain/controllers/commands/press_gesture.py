# nvdaMcpBridge domain -- PressGestureHandler: inject keyboard gestures in order.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# ROLE: command handler for `pressGesture`. Logs then presses each gesture in
# order, blocking until NVDA processed each. The first unresolvable id raises
# GestureError, which aborts the remainder; the Session turns that into an error
# Response (naming the id) and the session survives -- so error-wrapping stays in
# the dispatcher, not here.

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .... import protocol
from .command_handler import CommandHandler

if TYPE_CHECKING:
	from .session_context import SessionContext


class PressGestureHandler(CommandHandler):
	def execute(self, ctx: SessionContext, request: protocol.Request) -> Any:
		params = protocol.from_dict(protocol.PressGestureParams, request.params)
		for gesture_id in params.gestures:
			ctx.transcript.gesture(gesture_id)
			ctx.adapter_set.gesture_sender.press(gesture_id)
		return protocol.AckResult()
