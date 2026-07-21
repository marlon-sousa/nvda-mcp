# Unit tests for domain/controllers/session.py -- the LIFECYCLE + dispatcher.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# Since dispatch moved into command handlers, this module tests only what the
# Session itself owns: the handshake, the two watchdogs, teardown's
# restore-on-every-path invariant, and the dispatch MECHANICS (unknown command,
# a handler raising, the pre-hello gate, the resets_inactivity policy). The
# mechanics tests use FakeCommandHandler registries so they do not depend on what
# any real command does; the lifecycle tests use the real registry (with a fake
# AdapterFactory) because they exercise the real hello bootstrap and teardown.
#
# Per-command behaviour lives in tests/unit/domain/controllers/commands/. The
# teardown reason is asserted through the transcript's SESSION CLOSE event.

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any, Mapping

from fakes.adapter_factory import FakeAdapterFactory
from fakes.announcer import FakeAnnouncer
from fakes.clock import FakeClock
from fakes.command_handler import FakeCommandHandler
from fakes.message_channel import FakeChannel
from fakes.script import TIMEOUT_EVENT
from fakes.session_signals import FakeSessionSignals
from fakes.transcript import FakeTranscript

from nvdaMcpBridge import protocol as p
from nvdaMcpBridge.domain.controllers.commands.command_handler import CommandError, CommandHandler
from nvdaMcpBridge.domain.controllers.commands.registry import NVDA_CAPABILITIES, build_command_registry
from nvdaMcpBridge.domain.controllers.session import Session, SessionConfig, TeardownReason


# -- message builders --------------------------------------------------------


def hello(mode: str = "silent", *, version: int = p.PROTOCOL_VERSION, id: int = 1) -> dict[str, Any]:
	return {"id": id, "cmd": "hello", "params": {"mode": mode, "protocolVersion": version}}


def command(cmd: str, id: int, **params: Any) -> dict[str, Any]:
	return {"id": id, "cmd": cmd, "params": params}


# -- builder helper ----------------------------------------------------------


@dataclass
class Run:
	session: Session
	channel: FakeChannel
	transcript: FakeTranscript
	factory: FakeAdapterFactory
	clock: FakeClock
	signals: FakeSessionSignals

	def responses(self) -> list[dict[str, Any]]:
		return self.channel.responses()

	def closed_with(self, reason: TeardownReason) -> bool:
		return ("session_closed", reason.value) in self.transcript.events


def run_session(
	events: list[Any],
	*,
	clock: FakeClock | None = None,
	factory: FakeAdapterFactory | None = None,
	transcript: FakeTranscript | None = None,
	registry: Mapping[str, CommandHandler] | None = None,
	signals: FakeSessionSignals | None = None,
	announcer: FakeAnnouncer | None = None,
	on_empty: str = "closed",
	timeout_advance: float = 5.0,
	nvda_version: str = "2026.1.0",
	heartbeat_timeout: float = 30.0,
	inactivity_timeout: float = 120.0,
	start: bool = True,
) -> Run:
	clock = clock or FakeClock()
	factory = factory or FakeAdapterFactory()
	transcript = transcript or FakeTranscript()
	signals = signals or FakeSessionSignals()
	announcer = announcer or FakeAnnouncer()
	if registry is None:
		registry = build_command_registry(factory, nvda_version)
	channel = FakeChannel(events, clock=clock, timeout_advance=timeout_advance, on_empty=on_empty)
	config = SessionConfig(
		nvda_version=nvda_version,
		heartbeat_timeout=heartbeat_timeout,
		inactivity_timeout=inactivity_timeout,
	)
	session = Session(channel, transcript, clock, config, registry, signals, announcer)
	if start:
		session.run()
	return Run(
		session=session,
		channel=channel,
		transcript=transcript,
		factory=factory,
		clock=clock,
		signals=signals,
	)


def _result(response: dict[str, Any]) -> dict[str, Any]:
	assert response["error"] is None, f"expected a result, got error {response['error']!r}"
	return response["result"]


def _error(response: dict[str, Any]) -> str:
	assert response["error"] is not None, f"expected an error, got result {response['result']!r}"
	return response["error"]["message"]


def _fake_registry(**handlers: FakeCommandHandler) -> dict[str, CommandHandler]:
	"""A registry with a stand-in hello (so tests can reach ESTABLISHED) plus
	whatever fake handlers a mechanics test wants."""
	registry: dict[str, CommandHandler] = {p.Command.HELLO: FakeCommandHandler(available_before_hello=True)}
	registry.update(handlers)
	return registry


# -- handshake (real hello through the dispatcher) ---------------------------


def test_silent_hello_establishes_and_reports() -> None:
	run = run_session([hello("silent")])
	assert run.factory.built_mode is p.CaptureMode.SILENT
	assert run.signals.started == 1  # ascending cue on establish
	result = _result(run.responses()[0])
	assert result["mode"] == "silent"
	assert result["synth"] == "espeak"  # the real synth, read via the announcer
	assert result["reader"] == {"name": "nvda", "version": "2026.1.0"}
	assert result["capabilities"] == [c.value for c in NVDA_CAPABILITIES]
	assert result["logPath"] == run.transcript.path


def test_live_hello_establishes() -> None:
	run = run_session([hello("live")])
	assert run.factory.built_mode is p.CaptureMode.LIVE
	assert run.signals.started == 1
	assert _result(run.responses()[0])["mode"] == "live"


def test_version_mismatch_errors_and_never_builds() -> None:
	run = run_session([hello(version=p.PROTOCOL_VERSION + 1)])
	message = _error(run.responses()[0])
	assert str(p.PROTOCOL_VERSION) in message and str(p.PROTOCOL_VERSION + 1) in message
	assert run.factory.built_mode is None
	assert run.closed_with(TeardownReason.HANDSHAKE_FAILED)
	assert run.channel.closed is True


def test_first_message_not_hello_fails_handshake() -> None:
	run = run_session([command("ping", 1)])
	assert "expected hello" in _error(run.responses()[0])
	assert run.closed_with(TeardownReason.HANDSHAKE_FAILED)


def test_unreadable_first_line_fails_handshake_without_reply() -> None:
	run = run_session([p.ValidationError("bad line")])
	assert run.responses() == []
	assert run.closed_with(TeardownReason.HANDSHAKE_FAILED)


def test_bad_hello_params_fail_handshake() -> None:
	run = run_session([command("hello", 1, mode="bogus", protocolVersion=p.PROTOCOL_VERSION)])
	assert run.closed_with(TeardownReason.HANDSHAKE_FAILED)
	assert run.responses()[0]["error"] is not None


def test_silence_before_hello_times_out() -> None:
	run = run_session([], on_empty="timeout", timeout_advance=5.0, heartbeat_timeout=30.0)
	assert run.responses() == []
	assert run.closed_with(TeardownReason.HANDSHAKE_FAILED)


# -- watchdogs ---------------------------------------------------------------


def test_heartbeat_fires_when_no_message_arrives() -> None:
	run = run_session([hello()], on_empty="timeout", timeout_advance=5.0, heartbeat_timeout=30.0)
	assert run.closed_with(TeardownReason.HEARTBEAT_TIMEOUT)


def test_pings_hold_the_heartbeat_but_not_inactivity() -> None:
	# A ping every 10s keeps the 30s heartbeat alive, but pings do not reset the
	# 120s inactivity clock, so inactivity is what eventually fires.
	events: list[Any] = [hello()]
	for i in range(12):
		events.append(command("ping", 100 + i))
		events.append(TIMEOUT_EVENT)
	run = run_session(
		events,
		on_empty="timeout",
		timeout_advance=10.0,
		heartbeat_timeout=30.0,
		inactivity_timeout=120.0,
	)
	assert run.closed_with(TeardownReason.INACTIVITY_TIMEOUT)


# -- teardown: stop capture on every path (speech flows again) ---------------
# There is no synth to restore now: stopping the speech source unregisters the
# suppression filter, so NVDA speaks again. Each step is guarded, so a raise in
# one never skips the channel close or the end cue.


def test_teardown_stops_capture_even_when_the_transcript_raises_on_close() -> None:
	transcript = FakeTranscript(fail_on={"session_closed"})
	run = run_session([hello("silent")], transcript=transcript)
	assert run.factory.speech_source.stopped == 1
	assert run.channel.closed is True


def test_teardown_finishes_even_when_a_source_stop_raises() -> None:
	factory = FakeAdapterFactory()
	factory.speech_source.fail_stop = True
	run = run_session([hello("silent")], factory=factory)
	# The speech source stop raised, but the guard let braille stop, the end cue
	# fire, and the channel close still happen.
	assert factory.braille_source.stopped == 1
	assert run.signals.ended == 1
	assert run.channel.closed is True


def test_teardown_is_idempotent_when_called_twice() -> None:
	run = run_session([hello("silent")])
	run.session._teardown()  # type: ignore[attr-defined]
	assert run.factory.speech_source.stopped == 1
	assert run.signals.ended == 1


# -- dispatch mechanics (fake handlers) --------------------------------------


def test_unknown_command_errors_without_killing_the_session() -> None:
	registry = _fake_registry(ping=FakeCommandHandler(resets_inactivity=False))
	run = run_session([hello(), command("frobnicate", 2), command("ping", 3)], registry=registry)
	assert "unknown command" in _error(run.responses()[1])
	assert _result(run.responses()[2]) == {"ok": True}


def test_a_handler_fault_becomes_an_error_and_the_session_continues() -> None:
	registry = _fake_registry(
		boom=FakeCommandHandler(error=RuntimeError("kaboom")),
		ping=FakeCommandHandler(resets_inactivity=False),
	)
	run = run_session([hello(), command("boom", 2), command("ping", 3)], registry=registry)
	assert "kaboom" in _error(run.responses()[1])
	assert _result(run.responses()[2]) == {"ok": True}


def test_a_command_error_becomes_an_error_and_the_session_continues() -> None:
	registry = _fake_registry(
		nope=FakeCommandHandler(error=CommandError("not yet")),
		ping=FakeCommandHandler(resets_inactivity=False),
	)
	run = run_session([hello(), command("nope", 2), command("ping", 3)], registry=registry)
	assert "not yet" in _error(run.responses()[1])
	assert _result(run.responses()[2]) == {"ok": True}


def test_duplicate_hello_errors_without_killing_the_session() -> None:
	registry = _fake_registry(ping=FakeCommandHandler(resets_inactivity=False))
	run = run_session([hello(id=1), hello(id=2), command("ping", 3)], registry=registry)
	assert _error(run.responses()[1]) == "session already established"
	assert _result(run.responses()[2]) == {"ok": True}


def test_garbage_with_an_id_gets_an_error_and_the_session_continues() -> None:
	registry = _fake_registry(ping=FakeCommandHandler(resets_inactivity=False))
	run = run_session([hello(), {"id": 5, "cmd": 123}, command("ping", 6)], registry=registry)
	responses = run.responses()
	assert responses[1]["id"] == 5 and responses[1]["error"] is not None
	assert _result(responses[2]) == {"ok": True}


def test_unreadable_message_mid_session_is_noted_and_survives() -> None:
	registry = _fake_registry(ping=FakeCommandHandler(resets_inactivity=False))
	run = run_session([hello(), p.ValidationError("boom"), command("ping", 3)], registry=registry)
	assert any(event[0] == "note" for event in run.transcript.events)
	# The unreadable line draws no reply, so the ping ack is the second response.
	assert _result(run.responses()[1]) == {"ok": True}


# -- lifecycle commands through dispatch -------------------------------------


def test_bye_acks_then_tears_down() -> None:
	run = run_session([hello(), command("bye", 2)])
	assert _result(run.responses()[1]) == {"ok": True}
	assert run.closed_with(TeardownReason.CLIENT_BYE)
	assert run.channel.closed is True


def test_channel_close_tears_down() -> None:
	run = run_session([hello()])  # script runs out -> EOF -> ChannelClosed
	assert run.closed_with(TeardownReason.CHANNEL_CLOSED)


def test_gesture_error_becomes_an_error_and_the_session_survives() -> None:
	# The real press_gesture handler + a rejecting factory: GestureError is a
	# caught type in dispatch, so this proves that path end to end.
	factory = FakeAdapterFactory(reject=["bad"])
	run = run_session(
		[hello(), command("pressGesture", 2, gestures=["bad"]), command("ping", 3)],
		factory=factory,
	)
	assert "bad" in _error(run.responses()[1])
	assert _result(run.responses()[2]) == {"ok": True}


# -- external teardown -------------------------------------------------------


def test_request_teardown_from_another_thread_ends_the_loop() -> None:
	clock = FakeClock()
	factory = FakeAdapterFactory()
	transcript = FakeTranscript()
	signals = FakeSessionSignals()
	registry = build_command_registry(factory, "x")
	channel = FakeChannel([hello()], clock=clock, on_empty="timeout", timeout_advance=1.0)
	config = SessionConfig(nvda_version="x", heartbeat_timeout=1e9, inactivity_timeout=1e9)
	session = Session(channel, transcript, clock, config, registry, signals, FakeAnnouncer())

	thread = threading.Thread(target=session.run)
	thread.start()
	session.request_teardown(TeardownReason.EXTERNAL)
	thread.join(timeout=5.0)

	assert not thread.is_alive()
	assert ("session_closed", TeardownReason.EXTERNAL.value) in transcript.events
	assert factory.speech_source.stopped == 1
	assert signals.ended == 1
