# Unit tests for domain/controllers/commands/get_next_speech_index.py.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.

from __future__ import annotations

from fakes.clock import FakeClock
from support.context import make_context, request, speech_with

from nvdaMcpBridge.domain.controllers.commands.get_next_speech_index import GetNextSpeechIndexHandler


def test_next_index_moves_as_speech_arrives(clock: FakeClock) -> None:
	ctx = make_context(clock, speech=speech_with(clock))
	handler = GetNextSpeechIndexHandler()
	# Sentinel occupies index 0, so the first real capture will land at 1.
	assert handler.execute(ctx, request("getNextSpeechIndex")).index == 1
	ctx.speech_buffer.append(["x"])
	assert handler.execute(ctx, request("getNextSpeechIndex")).index == 2
