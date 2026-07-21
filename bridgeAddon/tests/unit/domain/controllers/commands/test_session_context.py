# Unit tests for domain/controllers/commands/session_context.py.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.

from __future__ import annotations

import pytest
from fakes.announcer import FakeAnnouncer
from fakes.clock import FakeClock
from fakes.transcript import FakeTranscript
from support.context import RecordingClose, speech_with

from nvdaMcpBridge.domain.controllers.commands.session_context import SessionContext
from nvdaMcpBridge.domain.controllers.teardown_reason import TeardownReason


def _bare(clock: FakeClock) -> SessionContext:
	return SessionContext(clock, FakeTranscript(), RecordingClose(), FakeAnnouncer())


def test_close_delegates_the_reason(clock: FakeClock) -> None:
	close = RecordingClose()
	ctx = SessionContext(clock, FakeTranscript(), close, FakeAnnouncer())
	ctx.close(TeardownReason.CLIENT_BYE)
	assert close.reasons == [TeardownReason.CLIENT_BYE]


def test_buffer_accessors_assert_before_hello_installs_them(clock: FakeClock) -> None:
	ctx = _bare(clock)
	with pytest.raises(AssertionError):
		_ = ctx.speech_buffer
	with pytest.raises(AssertionError):
		_ = ctx.braille_buffer
	with pytest.raises(AssertionError):
		_ = ctx.adapter_set


def test_accessors_return_what_was_installed(clock: FakeClock) -> None:
	ctx = _bare(clock)
	buffer = speech_with(clock)
	ctx.speech = buffer
	assert ctx.speech_buffer is buffer
