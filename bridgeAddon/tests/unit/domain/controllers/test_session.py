# Unit tests for domain/controllers/session.py.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# The Session is driven entirely through its ports, so these tests script a
# scenario per case and read back the replies the client would have seen and the
# transcript the tester would read. That is a BUILDER helper (run_session, with
# per-test overrides), not a fixture: every test varies the script, the factory,
# or the config, which is exactly the case AGENTS.md names for builders over
# fixtures.
#
# The teardown reason is asserted through the transcript's SESSION CLOSE event
# (the FakeTranscript records every call), so the tests stay behavioural rather
# than reaching into the controller's private state.

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any

from fakes.adapter_factory import FakeAdapterFactory
from fakes.clock import FakeClock
from fakes.message_channel import FakeChannel
from fakes.transcript import FakeTranscript

from nvdaMcpBridge import protocol as p
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
	channel = FakeChannel(events, clock=clock, timeout_advance=timeout_advance, on_empty=on_empty)
	config = SessionConfig(
		nvda_version=nvda_version,
		heartbeat_timeout=heartbeat_timeout,
		inactivity_timeout=inactivity_timeout,
	)
	session = Session(channel, transcript, clock, factory, config)
	if start:
		session.run()
	return Run(session=session, channel=channel, transcript=transcript, factory=factory, clock=clock)


def _result(response: dict[str, Any]) -> dict[str, Any]:
	assert response["error"] is None, f"expected a result, got error {response['error']!r}"
	return response["result"]


def _error(response: dict[str, Any]) -> str:
	assert response["error"] is not None, f"expected an error, got result {response['result']!r}"
	return response["error"]["message"]


# -- 1. valid silent hello ---------------------------------------------------


def test_silent_hello_builds_after_hello_swaps_and_reports() -> None:
	run = run_session([hello("silent")])

	# The factory was asked for SILENT, and only after hello (never earlier).
	assert run.factory.built_mode is p.CaptureMode.SILENT
	# Synth swapped; both sources started against the session's buffers.
	assert run.factory.synth_swapper.swaps == 1
	assert run.factory.speech_source.started == 1
	assert run.factory.braille_source.started == 1

	result = _result(run.responses()[0])
	assert result["protocolVersion"] == p.PROTOCOL_VERSION
	assert result["nvdaVersion"] == "2026.1.0"
	assert result["mode"] == "silent"
	assert result["synth"] == "espeak"
	assert result["logPath"] == run.transcript.path

	assert ("open",) in run.transcript.events
	assert ("session_opened", p.CaptureMode.SILENT, "espeak") in run.transcript.events
	assert ("synth_swapped", "espeak") in run.transcript.events


# -- 2. valid live hello -----------------------------------------------------


def test_live_hello_does_not_swap_the_synth() -> None:
	run = run_session([hello("live")])

	assert run.factory.built_mode is p.CaptureMode.LIVE
	assert run.factory.synth_swapper.swaps == 0
	result = _result(run.responses()[0])
	assert result["mode"] == "live"
	assert result["synth"] == "espeak"
	assert all(event[0] != "synth_swapped" for event in run.transcript.events)


# -- 3. version mismatch -----------------------------------------------------


def test_version_mismatch_errors_and_never_builds() -> None:
	run = run_session([hello(version=p.PROTOCOL_VERSION + 1)])

	message = _error(run.responses()[0])
	assert str(p.PROTOCOL_VERSION) in message and str(p.PROTOCOL_VERSION + 1) in message
	# The factory is never called on a mismatch, so there is no swap to undo;
	# teardown still runs cleanly to completion.
	assert run.factory.built_mode is None
	assert run.factory.synth_swapper.swaps == 0
	assert run.closed_with(TeardownReason.HANDSHAKE_FAILED)
	assert run.channel.closed is True


# -- 4. handshake failures ---------------------------------------------------


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
	assert "hello params" in _error(run.responses()[0])
	assert run.closed_with(TeardownReason.HANDSHAKE_FAILED)


def test_silence_before_hello_times_out() -> None:
	run = run_session([], on_empty="timeout", timeout_advance=5.0, heartbeat_timeout=30.0)
	assert run.responses() == []
	assert run.closed_with(TeardownReason.HANDSHAKE_FAILED)


# -- 5. speech + braille reads -----------------------------------------------


def test_speech_commands_read_from_the_buffer() -> None:
	factory = FakeAdapterFactory(speech={"NVDA+f7": ["Elements list dialog"]})
	run = run_session(
		[
			hello("silent"),
			command("getNextSpeechIndex", 2),
			command("pressGesture", 3, gestures=["NVDA+f7"]),
			command("getSpeech", 4, sinceIndex=0),
			command("getLastSpeech", 5),
			command("waitForSpeech", 6, text="Elements", afterIndex=0, timeout=1.0),
			command("waitForSpeechToFinish", 7, timeout=1.0),
		],
		factory=factory,
	)
	responses = run.responses()

	# Before any speech the next index is 1 (sentinel occupies index 0).
	assert _result(responses[1])["index"] == 1
	# pressGesture acked, and its scripted speech is now readable.
	assert _result(responses[2]) == {"ok": True}
	speech = _result(responses[3])
	assert "Elements list dialog" in speech["text"]
	assert speech["fromIndex"] == 0
	assert _result(responses[4])["text"] == "Elements list dialog"
	waited = _result(responses[5])
	assert waited["found"] is True and "Elements" in waited["text"]
	assert _result(responses[6])["finished"] is True


def test_get_braille_reads_from_the_buffer() -> None:
	factory = FakeAdapterFactory()
	factory.braille_source.initial = ["find:  █"]
	run = run_session([hello("silent"), command("getBraille", 2, sinceIndex=0)], factory=factory)
	braille = _result(run.responses()[1])
	assert "find:" in braille["text"]
	assert braille["fromIndex"] == 0


# -- 6. pressGesture ordering + GestureError ---------------------------------


def test_press_gesture_presses_in_order_and_logs_each() -> None:
	factory = FakeAdapterFactory()
	run = run_session([hello(), command("pressGesture", 2, gestures=["a", "b"])], factory=factory)
	assert factory.gesture_sender.pressed == ["a", "b"]
	assert _result(run.responses()[1]) == {"ok": True}
	gestures = [event for event in run.transcript.events if event[0] == "gesture"]
	assert gestures == [("gesture", "a"), ("gesture", "b")]


def test_gesture_error_aborts_the_rest_but_keeps_the_session() -> None:
	factory = FakeAdapterFactory(reject=["bad"])
	run = run_session(
		[hello(), command("pressGesture", 2, gestures=["a", "bad", "c"]), command("ping", 3)],
		factory=factory,
	)
	# "a" pressed, "bad" rejected, "c" never reached.
	assert factory.gesture_sender.pressed == ["a"]
	assert "bad" in _error(run.responses()[1])
	# Gesture logged up to and including the failing one.
	gestures = [event for event in run.transcript.events if event[0] == "gesture"]
	assert gestures == [("gesture", "a"), ("gesture", "bad")]
	# Session survived to answer the following ping.
	assert _result(run.responses()[2]) == {"ok": True}


# -- 7. watchdogs ------------------------------------------------------------


def test_heartbeat_fires_when_no_message_arrives() -> None:
	run = run_session(
		[hello()],
		on_empty="timeout",
		timeout_advance=5.0,
		heartbeat_timeout=30.0,
		inactivity_timeout=120.0,
	)
	assert run.closed_with(TeardownReason.HEARTBEAT_TIMEOUT)


def test_pings_hold_the_heartbeat_but_not_inactivity() -> None:
	# A ping every 10s keeps the 30s heartbeat alive, but pings do not reset the
	# 120s inactivity clock, so inactivity is what eventually fires.
	events: list[Any] = [hello()]
	from fakes.script import TIMEOUT_EVENT

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


# -- 8. bye + channel closed -------------------------------------------------


def test_bye_acks_then_tears_down() -> None:
	run = run_session([hello(), command("bye", 2)])
	assert _result(run.responses()[1]) == {"ok": True}
	assert run.closed_with(TeardownReason.CLIENT_BYE)
	assert run.channel.closed is True


def test_channel_close_tears_down() -> None:
	run = run_session([hello()])  # script runs out -> EOF -> ChannelClosed
	assert run.closed_with(TeardownReason.CHANNEL_CLOSED)


# -- 9. mid-session fault tolerance ------------------------------------------


def test_garbage_with_an_id_gets_an_error_and_the_session_continues() -> None:
	run = run_session([hello(), {"id": 5, "cmd": 123}, command("ping", 6)])
	responses = run.responses()
	assert responses[1]["id"] == 5 and responses[1]["error"] is not None
	assert _result(responses[2]) == {"ok": True}


def test_unreadable_message_is_noted_and_the_session_continues() -> None:
	run = run_session([hello(), p.ValidationError("boom"), command("bye", 3)])
	assert any(event[0] == "note" for event in run.transcript.events)
	assert run.closed_with(TeardownReason.CLIENT_BYE)


def test_a_handler_fault_becomes_an_error_and_the_session_continues() -> None:
	factory = FakeAdapterFactory()
	factory.gesture_sender.boom = {"kaboom"}
	run = run_session(
		[hello(), command("pressGesture", 2, gestures=["kaboom"]), command("ping", 3)],
		factory=factory,
	)
	assert "kaboom" in _error(run.responses()[1])
	assert _result(run.responses()[2]) == {"ok": True}


def test_duplicate_hello_errors_without_killing_the_session() -> None:
	run = run_session([hello(id=1), hello(id=2), command("bye", 3)])
	assert _error(run.responses()[1]) == "session already established"
	assert run.closed_with(TeardownReason.CLIENT_BYE)


def test_unknown_command_errors_without_killing_the_session() -> None:
	run = run_session([hello(), command("frobnicate", 2), command("bye", 3)])
	assert "unknown command" in _error(run.responses()[1])
	assert run.closed_with(TeardownReason.CLIENT_BYE)


def test_not_yet_implemented_command_errors_cleanly() -> None:
	run = run_session([hello(), command("getState", 2), command("bye", 3)])
	assert "not implemented" in _error(run.responses()[1])
	assert run.closed_with(TeardownReason.CLIENT_BYE)


# -- 10. restore on every teardown path --------------------------------------


def test_restore_runs_even_when_the_transcript_raises_on_close() -> None:
	transcript = FakeTranscript(fail_on={"session_closed"})
	run = run_session([hello("silent")], transcript=transcript)
	assert run.factory.synth_swapper.restores == 1
	assert run.channel.closed is True


def test_restore_runs_even_when_a_source_stop_raises() -> None:
	factory = FakeAdapterFactory()
	factory.speech_source.fail_stop = True
	run = run_session([hello("silent")], factory=factory)
	assert factory.synth_swapper.restores == 1
	assert run.channel.closed is True


def test_a_failing_restore_does_not_block_the_channel_close() -> None:
	factory = FakeAdapterFactory(fail_restore=True)
	run = run_session([hello("silent")], factory=factory)
	assert factory.synth_swapper.restores == 1
	assert run.channel.closed is True


def test_restore_is_idempotent_when_called_twice() -> None:
	run = run_session([hello("silent")])
	# Teardown already restored once; a second teardown must be a harmless no-op
	# (run() is guarded by _torn_down, so this exercises the contract directly).
	run.session._teardown()  # type: ignore[attr-defined]
	assert run.factory.synth_swapper.restores == 1


# -- 11. external teardown ---------------------------------------------------


def test_request_teardown_from_another_thread_ends_the_loop() -> None:
	clock = FakeClock()
	factory = FakeAdapterFactory()
	transcript = FakeTranscript()
	channel = FakeChannel([hello()], clock=clock, on_empty="timeout", timeout_advance=1.0)
	config = SessionConfig(nvda_version="x", heartbeat_timeout=1e9, inactivity_timeout=1e9)
	session = Session(channel, transcript, clock, factory, config)

	thread = threading.Thread(target=session.run)
	thread.start()
	session.request_teardown(TeardownReason.EXTERNAL)
	thread.join(timeout=5.0)

	assert not thread.is_alive()
	assert ("session_closed", TeardownReason.EXTERNAL.value) in transcript.events
	assert factory.synth_swapper.restores == 1
