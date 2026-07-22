# Unit tests for domain/controllers/commands/get_braille.py.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.

from __future__ import annotations

from fakes.clock import FakeClock
from support.context import braille_with, make_context, request

from nvdaMcpBridge import protocol as p
from nvdaMcpBridge.domain.controllers.commands.get_braille import GetBrailleHandler


def test_get_braille_reads_since_index(clock: FakeClock) -> None:
	ctx = make_context(clock, braille=braille_with(clock, "find: x"))
	result = GetBrailleHandler().execute(ctx, request("getBraille", sinceIndex=0))
	assert isinstance(result, p.BrailleResult)
	assert "find:" in result.text
	assert result.fromIndex == 0
