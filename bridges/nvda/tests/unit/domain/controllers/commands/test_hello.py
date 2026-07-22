# Unit tests for domain/controllers/commands/hello.py.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.

from __future__ import annotations

import pytest
from fakes.adapter_factory import FakeAdapterFactory
from fakes.clock import FakeClock
from fakes.log_capture import FakeLogCapture
from fakes.transcript import FakeTranscript
from support.context import make_context

from nvdaMcpBridge import protocol as p
from nvdaMcpBridge.domain.controllers.commands.command_handler import CommandError
from nvdaMcpBridge.domain.controllers.commands.hello import HelloHandler
from nvdaMcpBridge.domain.controllers.commands.registry import NVDA_CAPABILITIES


def _hello(
	mode: str, version: int = p.PROTOCOL_VERSION, *, log_level: p.LogLevel | None = None
) -> p.Request:
	params: dict[str, object] = {"mode": mode, "protocolVersion": version}
	if log_level is not None:
		params["logLevel"] = log_level.value
	return p.Request(id=1, cmd="hello", params=params)


def _handler(factory: FakeAdapterFactory, version: str = "2026.1.0") -> HelloHandler:
	# The bridge stamps its NVDA identity + the capabilities it serves (as wiring
	# does): speech/braille/gestures, not the full enum -- see NVDA_CAPABILITIES.
	return HelloHandler(factory, p.ReaderInfo(name="nvda", version=version), list(NVDA_CAPABILITIES))


def test_silent_hello_builds_and_reports(clock: FakeClock) -> None:
	factory = FakeAdapterFactory()
	transcript = FakeTranscript()
	log_capture = FakeLogCapture()
	ctx = make_context(clock, transcript=transcript, log_capture=log_capture)
	result = _handler(factory).execute(ctx, _hello("silent"))

	assert factory.built_mode is p.CaptureMode.SILENT
	assert factory.speech_source.started == 1 and factory.braille_source.started == 1
	assert factory.speech_source.buffer is ctx.speech

	assert isinstance(result, p.HelloResult)
	assert result.mode is p.CaptureMode.SILENT
	# The real synth is read via the announcer and never swapped.
	assert result.synth == "espeak"
	assert result.reader == p.ReaderInfo(name="nvda", version="2026.1.0")
	assert result.capabilities == list(NVDA_CAPABILITIES)
	assert result.logPath == transcript.path
	assert result.nvdaLogPath == log_capture.path

	# No logLevel requested -- capture still starts, just with no level change.
	assert log_capture.events == [("start", None)]

	# No synth swap event -- the synth is left loaded; capture is via the filter.
	assert transcript.events[:2] == [
		("open",),
		("session_opened", p.CaptureMode.SILENT, "espeak"),
	]
	assert all(event[0] != "synth_swapped" for event in transcript.events)


def test_hello_with_log_level_starts_capture_at_that_level(clock: FakeClock) -> None:
	factory = FakeAdapterFactory()
	log_capture = FakeLogCapture()
	ctx = make_context(clock, log_capture=log_capture)
	_handler(factory).execute(ctx, _hello("silent", log_level=p.LogLevel.DEBUG))

	assert log_capture.events == [("start", p.LogLevel.DEBUG)]


def test_live_hello_builds_and_reports(clock: FakeClock) -> None:
	factory = FakeAdapterFactory()
	transcript = FakeTranscript()
	ctx = make_context(clock, transcript=transcript)
	result = _handler(factory, "x").execute(ctx, _hello("live"))

	assert factory.built_mode is p.CaptureMode.LIVE
	assert isinstance(result, p.HelloResult)
	assert result.mode is p.CaptureMode.LIVE
	assert all(event[0] != "synth_swapped" for event in transcript.events)


def test_version_mismatch_raises_before_building(clock: FakeClock) -> None:
	factory = FakeAdapterFactory()
	transcript = FakeTranscript()
	log_capture = FakeLogCapture()
	ctx = make_context(clock, transcript=transcript, log_capture=log_capture)
	with pytest.raises(CommandError) as exc:
		_handler(factory, "x").execute(ctx, _hello("silent", p.PROTOCOL_VERSION + 1))

	message = str(exc.value)
	assert str(p.PROTOCOL_VERSION) in message and str(p.PROTOCOL_VERSION + 1) in message
	assert factory.built_mode is None
	assert transcript.opened is False
	assert log_capture.events == []


def test_captured_speech_flows_to_the_transcript(clock: FakeClock) -> None:
	factory = FakeAdapterFactory()
	transcript = FakeTranscript()
	ctx = make_context(clock, transcript=transcript)
	_handler(factory, "x").execute(ctx, _hello("silent"))
	ctx.speech_buffer.append(["Elements list"])
	assert ("speech", "Elements list") in transcript.events
