# Unit tests for domain/controllers/commands/hello.py.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.

from __future__ import annotations

import pytest
from fakes.adapter_factory import FakeAdapterFactory
from fakes.clock import FakeClock
from fakes.transcript import FakeTranscript
from support.context import make_context, request

from nvdaMcpBridge import protocol as p
from nvdaMcpBridge.domain.controllers.commands.command_handler import CommandError
from nvdaMcpBridge.domain.controllers.commands.hello import HelloHandler


def _hello(mode: str, version: int = p.PROTOCOL_VERSION) -> p.Request:
	return request("hello", mode=mode, protocolVersion=version)


def _handler(factory: FakeAdapterFactory, version: str = "2026.1.0") -> HelloHandler:
	# The bridge stamps its NVDA identity + full capability set (as wiring does).
	return HelloHandler(factory, p.ReaderInfo(name="nvda", version=version), list(p.Capability))


def test_silent_hello_builds_swaps_and_reports(clock: FakeClock) -> None:
	factory = FakeAdapterFactory()
	transcript = FakeTranscript()
	ctx = make_context(clock, transcript=transcript)
	result = _handler(factory).execute(ctx, _hello("silent"))

	assert factory.built_mode is p.CaptureMode.SILENT
	assert factory.speech_source.started == 1 and factory.braille_source.started == 1
	assert factory.speech_source.buffer is ctx.speech
	assert factory.synth_swapper.swaps == 1
	assert ctx.swapped_real == "espeak"

	assert isinstance(result, p.HelloResult)
	assert result.mode is p.CaptureMode.SILENT
	assert result.synth == "espeak"
	assert result.reader == p.ReaderInfo(name="nvda", version="2026.1.0")
	assert result.capabilities == list(p.Capability)
	assert result.logPath == transcript.path

	assert transcript.events[:3] == [
		("open",),
		("session_opened", p.CaptureMode.SILENT, "espeak"),
		("synth_swapped", "espeak"),
	]


def test_live_hello_does_not_swap(clock: FakeClock) -> None:
	factory = FakeAdapterFactory()
	transcript = FakeTranscript()
	ctx = make_context(clock, transcript=transcript)
	result = _handler(factory, "x").execute(ctx, _hello("live"))

	assert factory.synth_swapper.swaps == 0
	assert ctx.swapped_real is None
	assert isinstance(result, p.HelloResult)
	assert result.mode is p.CaptureMode.LIVE
	assert all(event[0] != "synth_swapped" for event in transcript.events)


def test_version_mismatch_raises_before_building(clock: FakeClock) -> None:
	factory = FakeAdapterFactory()
	transcript = FakeTranscript()
	ctx = make_context(clock, transcript=transcript)
	with pytest.raises(CommandError) as exc:
		_handler(factory, "x").execute(ctx, _hello("silent", p.PROTOCOL_VERSION + 1))

	message = str(exc.value)
	assert str(p.PROTOCOL_VERSION) in message and str(p.PROTOCOL_VERSION + 1) in message
	assert factory.built_mode is None
	assert transcript.opened is False


def test_captured_speech_flows_to_the_transcript(clock: FakeClock) -> None:
	factory = FakeAdapterFactory()
	transcript = FakeTranscript()
	ctx = make_context(clock, transcript=transcript)
	_handler(factory, "x").execute(ctx, _hello("silent"))
	ctx.speech_buffer.append(["Elements list"])
	assert ("speech", "Elements list") in transcript.events
