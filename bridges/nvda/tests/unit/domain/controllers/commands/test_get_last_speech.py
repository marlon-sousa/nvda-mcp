# Unit tests for domain/controllers/commands/get_last_speech.py.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.

from __future__ import annotations

from fakes.clock import FakeClock
from support.context import make_context, request, speech_with

from nvdaMcpBridge import protocol as p
from nvdaMcpBridge.domain.controllers.commands.get_last_speech import GetLastSpeechHandler


def test_get_last_speech(clock: FakeClock) -> None:
	ctx = make_context(clock, speech=speech_with(clock, "one", "last"))
	result = GetLastSpeechHandler().execute(ctx, request("getLastSpeech"))
	assert isinstance(result, p.LastSpeechResult)
	assert result.text == "last"
	assert result.index == 2
