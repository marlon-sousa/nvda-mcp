# nvdaMcpBridge tests -- builders for command-handler tests.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# A command handler is testable with a hand-built SessionContext and no Session
# at all -- that is the point of splitting dispatch out. make_context assembles
# one from fakes; each test seeds only the pieces its handler touches. These are
# builders, not fixtures, because every handler wants a different shape (AGENTS.md
# fixture policy).

from __future__ import annotations

from typing import TYPE_CHECKING

from fakes.announcer import FakeAnnouncer
from fakes.transcript import FakeTranscript

from nvdaMcpBridge import protocol as p
from nvdaMcpBridge.domain.controllers.commands.session_context import SessionContext
from nvdaMcpBridge.domain.entities.braille_buffer import BrailleBuffer
from nvdaMcpBridge.domain.entities.speech_buffer import SpeechBuffer

if TYPE_CHECKING:
	from fakes.adapter_factory import FakeAdapterFactory
	from fakes.clock import FakeClock
	from nvdaMcpBridge.domain.controllers.teardown_reason import TeardownReason
	from nvdaMcpBridge.domain.ports.adapter_factory import AdapterSet


class RecordingClose:
	"""Captures the reason a handler asked the session to close with."""

	def __init__(self) -> None:
		self.reasons: list[TeardownReason] = []

	def __call__(self, reason: TeardownReason) -> None:
		self.reasons.append(reason)


def make_context(
	clock: FakeClock,
	*,
	transcript: FakeTranscript | None = None,
	speech: SpeechBuffer | None = None,
	braille: BrailleBuffer | None = None,
	adapters: AdapterSet | None = None,
	close: RecordingClose | None = None,
	announcer: FakeAnnouncer | None = None,
) -> SessionContext:
	"""Build a SessionContext for a handler test, seeded with only what it needs."""
	ctx = SessionContext(
		clock,
		transcript or FakeTranscript(),
		close or RecordingClose(),
		announcer or FakeAnnouncer(),
	)
	ctx.speech = speech
	ctx.braille = braille
	ctx.adapters = adapters
	return ctx


def speech_with(clock: FakeClock, *lines: str, exact_finish: bool = True) -> SpeechBuffer:
	buffer = SpeechBuffer(clock, exact_finish=exact_finish)
	for line in lines:
		buffer.append([line])
	if lines:
		buffer.notify_finished()
	return buffer


def braille_with(clock: FakeClock, *lines: str) -> BrailleBuffer:
	buffer = BrailleBuffer(clock)
	for line in lines:
		buffer.append(line)
	return buffer


def request(cmd: str, id: int = 1, **params: object) -> p.Request:
	return p.Request(id=id, cmd=cmd, params=dict(params))


def adapters_from(factory: FakeAdapterFactory) -> AdapterSet:
	"""The AdapterSet a factory would hand a session (mode is arbitrary here)."""
	return factory.build(p.CaptureMode.SILENT)
