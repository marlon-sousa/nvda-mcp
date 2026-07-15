# Tests for the Session controller, driven end to end through wiring.serve()
# with fake ports. Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2.
#
# These script whole MESSAGES against a FakeChannel: framing and JSON are the
# JsonLinesChannel adapter's job and are tested in test_json_lines_channel.py,
# so these tests stay about what the session actually decides -- handshake,
# dispatch, the two watchdogs, and synth restoration on every teardown path.

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from fakes import (
	TIMEOUT_EVENT,
	FakeAdapterFactory,
	FakeChannel,
	FakeClock,
	FakeGestureSender,
	FakeSpeechSource,
	FakeSynthSwapper,
	FakeTranscript,
)

from nvdaMcpBridge import protocol as p
from nvdaMcpBridge import wiring
from nvdaMcpBridge.domain.controllers.session import SessionConfig, TeardownReason

NVDA_VERSION = "2026.1.0"


@dataclass
class Ran:
	reason: TeardownReason
	responses: list[dict[str, Any]]
	source: FakeSpeechSource
	swapper: FakeSynthSwapper
	sender: FakeGestureSender
	transcript: FakeTranscript
	factory: FakeAdapterFactory
	channel: FakeChannel


def run_session(
	messages: list[Any],
	*,
	clock: FakeClock | None = None,
	swapper: FakeSynthSwapper | None = None,
	sender: FakeGestureSender | None = None,
	config: SessionConfig | None = None,
	on_empty: str = "closed",
	timeout_advance: float = 5.0,
	prepare: Callable[[FakeSpeechSource], None] | None = None,
) -> Ran:
	clock = clock or FakeClock()
	source = FakeSpeechSource(clock)
	swapper = swapper or FakeSynthSwapper()
	sender = sender or FakeGestureSender()
	if prepare is not None:
		prepare(source)
	factory = FakeAdapterFactory(source, swapper, sender)
	transcript = FakeTranscript()
	channel = FakeChannel(messages, clock=clock, on_empty=on_empty, timeout_advance=timeout_advance)
	reason = wiring.serve(
		channel,
		clock=clock,
		transcript=transcript,
		factory=factory,
		nvda_version=NVDA_VERSION,
		config=config,
	)
	return Ran(reason, channel.responses(), source, swapper, sender, transcript, factory, channel)


def _hello(mode: str = "silent", version: int = p.PROTOCOL_VERSION) -> dict[str, Any]:
	return {"id": 1, "cmd": "hello", "params": {"mode": mode, "protocolVersion": version}}


# -- handshake ----------------------------------------------------------------


def test_silent_handshake_swaps_synth_and_reports_state() -> None:
	ran = run_session([_hello("silent"), {"id": 2, "cmd": "bye"}])
	hello = ran.responses[0]
	assert hello["id"] == 1
	assert hello["result"] == {
		"protocolVersion": 1,
		"nvdaVersion": NVDA_VERSION,
		"mode": "silent",
		"synth": "espeak",
		"logPath": ran.transcript.path,
	}
	assert ran.swapper.swap_count == 1
	assert ran.factory.built_mode is p.CaptureMode.SILENT
	assert ran.source.started is True
	assert ran.reason is TeardownReason.CLIENT_BYE


def test_live_handshake_does_not_touch_the_synth() -> None:
	ran = run_session([_hello("live"), {"id": 2, "cmd": "bye"}])
	assert ran.swapper.swap_count == 0
	assert ran.factory.built_mode is p.CaptureMode.LIVE
	assert ran.reason is TeardownReason.CLIENT_BYE


def test_protocol_version_mismatch_is_rejected_before_any_swap() -> None:
	ran = run_session([_hello("silent", version=99)])
	assert ran.reason is TeardownReason.PROTOCOL_ERROR
	assert "protocol version mismatch" in ran.responses[0]["error"]["message"]
	assert ran.swapper.swap_count == 0
	# The factory is never asked to build when the handshake fails.
	assert ran.factory.built_mode is None


def test_unknown_mode_is_rejected() -> None:
	ran = run_session([_hello("shouting")])
	assert ran.reason is TeardownReason.PROTOCOL_ERROR
	assert "not a valid CaptureMode" in ran.responses[0]["error"]["message"]


def test_first_message_must_be_hello() -> None:
	ran = run_session([{"id": 1, "cmd": "ping"}])
	assert ran.reason is TeardownReason.PROTOCOL_ERROR
	assert "expected 'hello' first" in ran.responses[0]["error"]["message"]


def test_second_hello_is_rejected() -> None:
	ran = run_session([_hello("live"), _hello("live"), {"id": 3, "cmd": "bye"}])
	assert ran.responses[1]["error"]["message"].startswith("already connected")


# -- teardown always restores -------------------------------------------------


def test_bye_restores_synth_and_closes_transcript() -> None:
	ran = run_session([_hello("silent"), {"id": 2, "cmd": "bye"}])
	assert ran.swapper.restore_count == 1
	assert ran.swapper.swapped is False
	assert "SYNTH RESTORE -> espeak" in ran.transcript.lines
	assert ran.transcript.closed_reason == "client-bye"
	assert ran.channel.closed is True


def test_client_disconnect_still_restores_synth() -> None:
	# No bye; the channel reports closed straight after the handshake.
	ran = run_session([_hello("silent")])
	assert ran.reason is TeardownReason.CLIENT_CLOSED
	assert ran.swapper.restore_count == 1
	assert ran.swapper.swapped is False


def test_restore_failure_is_contained_and_still_logged() -> None:
	swapper = FakeSynthSwapper(raise_on_restore=True)
	ran = run_session([_hello("silent"), {"id": 2, "cmd": "bye"}], swapper=swapper)
	# serve() must not raise; the restore was attempted and the failure noted.
	assert ran.reason is TeardownReason.CLIENT_BYE
	assert swapper.restore_count == 1
	assert any("synth restore raised" in line for line in ran.transcript.lines)


# -- timeouts -----------------------------------------------------------------


def test_heartbeat_timeout_when_client_goes_silent() -> None:
	ran = run_session(
		[_hello("silent")],
		config=SessionConfig(heartbeat_timeout=30.0, inactivity_timeout=120.0),
		on_empty="timeout",
	)
	assert ran.reason is TeardownReason.HEARTBEAT_TIMEOUT
	assert ran.swapper.restore_count == 1


def test_inactivity_timeout_fires_even_though_pings_keep_heartbeat_alive() -> None:
	# Heartbeat effectively disabled; a ping refreshes the heartbeat but not the
	# command-activity clock, so inactivity must still fire -- and it fires on
	# schedule from the handshake, proving the ping did not defer it.
	ran = run_session(
		[
			_hello("live"),
			TIMEOUT_EVENT,  # t=+4
			{"id": 2, "cmd": "ping"},  # refreshes heartbeat only
			TIMEOUT_EVENT,  # t=+8
		],
		config=SessionConfig(heartbeat_timeout=10_000.0, inactivity_timeout=10.0),
		on_empty="timeout",
		timeout_advance=4.0,
	)
	assert ran.reason is TeardownReason.INACTIVITY_TIMEOUT
	assert {"id": 2, "result": {"ok": True}, "error": None} in ran.responses


# -- command dispatch ---------------------------------------------------------


def test_press_gesture_emulates_each_and_logs_them() -> None:
	ran = run_session(
		[
			_hello("live"),
			{"id": 2, "cmd": "pressGesture", "params": {"gestures": ["NVDA+f7", "downArrow"]}},
			{"id": 3, "cmd": "bye"},
		],
	)
	assert ran.sender.sent == ["NVDA+f7", "downArrow"]
	assert ran.responses[1]["result"] == {"ok": True}
	assert "GESTURE NVDA+f7" in ran.transcript.lines
	assert "GESTURE downArrow" in ran.transcript.lines


def test_bad_gesture_reports_error_after_sending_the_good_ones() -> None:
	sender = FakeGestureSender(invalid={"bogus+key"})
	ran = run_session(
		[
			_hello("live"),
			{"id": 2, "cmd": "pressGesture", "params": {"gestures": ["NVDA+f7", "bogus+key"]}},
			{"id": 3, "cmd": "bye"},
		],
		sender=sender,
	)
	assert ran.sender.sent == ["NVDA+f7"]
	assert "bad gesture 'bogus+key'" in ran.responses[1]["error"]["message"]


def test_captured_speech_reaches_the_transcript_unfetched() -> None:
	# The session wires the speech buffer's observer to the Transcript port, so
	# speech NVDA emits mid-session is recorded bridge-side even though the agent
	# never asked for it. The callable script entry is NVDA speaking mid-run.
	holder: list[FakeSpeechSource] = []
	ran = run_session(
		[
			_hello("live"),
			lambda: holder[0].emit_speech("Find ", "dialog"),
			{"id": 2, "cmd": "bye"},
		],
		prepare=holder.append,
	)
	assert "SPEECH 'Find dialog'" in ran.transcript.lines


def test_speech_captured_before_the_session_is_not_transcribed() -> None:
	# The observer is only wired for the session's lifetime, so earlier chatter
	# stays in the buffer but never lands in this session's transcript.
	ran = run_session(
		[_hello("live"), {"id": 2, "cmd": "bye"}],
		prepare=lambda s: s.emit_speech("earlier chatter"),
	)
	assert not any("earlier chatter" in line for line in ran.transcript.lines)


def test_speech_reads_reflect_the_buffer() -> None:
	def prepare(source: FakeSpeechSource) -> None:
		source.emit_speech("Find")  # index 1
		source.emit_speech("dialog")  # index 2

	ran = run_session(
		[
			_hello("live"),
			{"id": 2, "cmd": "getNextSpeechIndex"},
			{"id": 3, "cmd": "getSpeech", "params": {"sinceIndex": 1}},
			{"id": 4, "cmd": "getLastSpeech"},
			{"id": 5, "cmd": "bye"},
		],
		prepare=prepare,
	)
	assert ran.responses[1]["result"] == {"index": 3}
	assert ran.responses[2]["result"] == {"text": "Find\ndialog", "fromIndex": 1, "toIndex": 3}
	assert ran.responses[3]["result"] == {"text": "dialog", "index": 2}


def test_wait_for_speech_finds_existing_text() -> None:
	ran = run_session(
		[
			_hello("live"),
			{"id": 2, "cmd": "waitForSpeech", "params": {"text": "ready", "timeout": 1}},
			{"id": 3, "cmd": "bye"},
		],
		prepare=lambda s: s.emit_speech("system ready"),
	)
	assert ran.responses[1]["result"] == {"found": True, "index": 1, "text": "system ready"}


def test_wait_for_speech_to_finish_true_in_live_mode() -> None:
	ran = run_session(
		[
			_hello("live"),
			{"id": 2, "cmd": "waitForSpeechToFinish", "params": {"timeout": 5}},
			{"id": 3, "cmd": "bye"},
		],
		prepare=lambda s: s.emit_speech("talking"),
	)
	assert ran.responses[1]["result"] == {"finished": True}


def test_get_braille_reads_the_braille_buffer() -> None:
	ran = run_session(
		[
			_hello("live"),
			{"id": 2, "cmd": "getBraille", "params": {"sinceIndex": 1}},
			{"id": 3, "cmd": "bye"},
		],
		prepare=lambda s: s.emit_braille("brl text"),
	)
	assert ran.responses[1]["result"] == {"text": "brl text", "fromIndex": 1, "toIndex": 2}


def test_unknown_command_is_reported() -> None:
	ran = run_session([_hello("live"), {"id": 2, "cmd": "teleport"}, {"id": 3, "cmd": "bye"}])
	assert "unknown command 'teleport'" in ran.responses[1]["error"]["message"]


def test_introspection_commands_report_not_yet_supported() -> None:
	ran = run_session([_hello("live"), {"id": 2, "cmd": "getState"}, {"id": 3, "cmd": "bye"}])
	assert "not supported by this bridge build" in ran.responses[1]["error"]["message"]


def test_malformed_frame_is_reported_and_the_loop_continues() -> None:
	# A frame missing the required 'cmd' after a good handshake.
	ran = run_session(
		[_hello("live"), {"id": 2}, {"id": 3, "cmd": "ping"}, {"id": 4, "cmd": "bye"}],
	)
	assert "malformed request" in ran.responses[1]["error"]["message"]
	# The session kept going and answered the following ping.
	assert ran.responses[2] == {"id": 3, "result": {"ok": True}, "error": None}
	assert ran.reason is TeardownReason.CLIENT_BYE


def test_unreadable_message_is_reported_and_the_loop_continues() -> None:
	# Garbage bytes surface as ValidationError out of the channel. That must not
	# take the session down (and so must never skip the synth restore).
	ran = run_session(
		[
			_hello("silent"),
			p.ValidationError("malformed JSON line: boom"),
			{"id": 3, "cmd": "ping"},
			{"id": 4, "cmd": "bye"},
		],
	)
	assert "unreadable message" in ran.responses[1]["error"]["message"]
	assert ran.responses[2] == {"id": 3, "result": {"ok": True}, "error": None}
	assert ran.reason is TeardownReason.CLIENT_BYE
	assert ran.swapper.restore_count == 1
