# Unit tests for domain/controllers/commands/ping.py.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.

from __future__ import annotations

from fakes.clock import FakeClock
from support.context import make_context, request

from nvdaMcpBridge import protocol as p
from nvdaMcpBridge.domain.controllers.commands.ping import PingHandler


def test_ping_returns_ack(clock: FakeClock) -> None:
	result = PingHandler().execute(make_context(clock), request("ping"))
	assert isinstance(result, p.AckResult)


def test_ping_does_not_reset_inactivity() -> None:
	assert PingHandler.resets_inactivity is False
