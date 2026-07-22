# Unit tests for domain/controllers/commands/wait_for_speech_to_finish.py.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.

from __future__ import annotations

from fakes.clock import FakeClock
from support.context import make_context, request, speech_with

from nvdaMcpBridge.domain.controllers.commands.wait_for_speech_to_finish import (
	WaitForSpeechToFinishHandler,
)


def test_finished_once_speech_is_done(clock: FakeClock) -> None:
	# speech_with fires notify_finished, so exact-mode "finished" is already true.
	ctx = make_context(clock, speech=speech_with(clock, "done"))
	result = WaitForSpeechToFinishHandler().execute(ctx, request("waitForSpeechToFinish", timeout=1.0))
	assert result.finished is True
