# nvdaMcpBridge tests -- FakeCommandHandler, standing in for a CommandHandler.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# FAKES: domain/controllers/commands/command_handler.py
#
# Lets the Session's DISPATCH mechanics be tested without any real command logic:
# a registry of these proves unknown-command handling, error wrapping when a
# handler raises, the resets_inactivity / available_before_hello policy, and the
# pre-hello gate -- none of which should depend on what getSpeech or pressGesture
# actually do. It records the contexts/requests it was called with and returns a
# canned result or raises a canned exception.

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from nvdaMcpBridge import protocol as p
from nvdaMcpBridge.domain.controllers.commands.command_handler import CommandHandler

if TYPE_CHECKING:
	from nvdaMcpBridge.domain.controllers.commands.session_context import SessionContext


class FakeCommandHandler(CommandHandler):
	"""A scriptable handler: returns ``result`` or raises ``error``."""

	def __init__(
		self,
		*,
		result: Any = None,
		error: Exception | None = None,
		resets_inactivity: bool = True,
		available_before_hello: bool = False,
	) -> None:
		self._result = result if result is not None else p.AckResult()
		self._error = error
		self.resets_inactivity = resets_inactivity
		self.available_before_hello = available_before_hello
		self.calls: list[p.Request] = []

	def execute(self, ctx: SessionContext, request: p.Request) -> Any:
		self.calls.append(request)
		if self._error is not None:
			raise self._error
		return self._result
