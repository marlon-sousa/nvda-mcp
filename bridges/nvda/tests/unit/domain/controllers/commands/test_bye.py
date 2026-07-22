# Unit tests for domain/controllers/commands/bye.py.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.

from __future__ import annotations

from fakes.clock import FakeClock
from support.context import RecordingClose, make_context, request

from nvdaMcpBridge import protocol as p
from nvdaMcpBridge.domain.controllers.commands.bye import ByeHandler
from nvdaMcpBridge.domain.controllers.teardown_reason import TeardownReason


def test_bye_acks_and_asks_to_close(clock: FakeClock) -> None:
	close = RecordingClose()
	ctx = make_context(clock, close=close)
	result = ByeHandler().execute(ctx, request("bye"))
	assert isinstance(result, p.AckResult)
	assert close.reasons == [TeardownReason.CLIENT_BYE]
