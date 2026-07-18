# Unit tests for domain/controllers/commands/echo.py.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.

from __future__ import annotations

import pytest
from fakes.clock import FakeClock
from support.context import make_context, request

from nvdaMcpBridge import protocol as p
from nvdaMcpBridge.domain.controllers.commands.echo import EchoHandler


@pytest.mark.parametrize(
	"payload",
	[
		"olá café",
		{"nested": [1, 2, {"deep": True}], "n": 3.5},
		[True, None, "mix", 42],
	],
)
def test_echo_returns_the_payload_unchanged(clock: FakeClock, payload: object) -> None:
	result = EchoHandler().execute(make_context(clock), request("echo", payload=payload))
	assert isinstance(result, p.EchoResult)
	assert result.payload == payload
