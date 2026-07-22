# Unit tests for domain/controllers/commands/get_speech.py.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.

from __future__ import annotations

from fakes.clock import FakeClock
from support.context import make_context, request, speech_with

from nvdaMcpBridge import protocol as p
from nvdaMcpBridge.domain.controllers.commands.get_speech import GetSpeechHandler


def test_get_speech_reads_since_index(clock: FakeClock) -> None:
	ctx = make_context(clock, speech=speech_with(clock, "one", "two"))
	result = GetSpeechHandler().execute(ctx, request("getSpeech", sinceIndex=0))
	assert isinstance(result, p.SpeechResult)
	assert "one" in result.text and "two" in result.text
	assert result.fromIndex == 0
	assert result.toIndex == 3
