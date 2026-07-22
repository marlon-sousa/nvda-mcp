# Unit tests for domain/controllers/commands/wait_for_speech.py.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.

from __future__ import annotations

from fakes.clock import FakeClock
from support.context import make_context, request, speech_with

from nvdaMcpBridge.domain.controllers.commands.wait_for_speech import WaitForSpeechHandler


def test_wait_for_speech_found(clock: FakeClock) -> None:
	ctx = make_context(clock, speech=speech_with(clock, "Find dialog"))
	result = WaitForSpeechHandler().execute(
		ctx, request("waitForSpeech", text="Find", afterIndex=0, timeout=1.0)
	)
	assert result.found is True
	assert "Find" in result.text


def test_wait_for_speech_not_found_returns_a_fresh_bookmark(clock: FakeClock) -> None:
	ctx = make_context(clock, speech=speech_with(clock, "hello"))
	result = WaitForSpeechHandler().execute(
		ctx, request("waitForSpeech", text="absent", afterIndex=0, timeout=0.0)
	)
	assert result.found is False
	assert result.text == ""
