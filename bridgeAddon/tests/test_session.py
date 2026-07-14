# Tests for the session state machine, driven end to end through Session.run()
# with fake adapters + a scripted transport. Copyright (C) 2026 Marlon Brandao
# de Sousa. GPL-2. See COPYING.txt.

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from fakes import FakeClock, FakeGestureSender, FakeSpeechSource, FakeSynthSwapper, FakeTransport

from nvdaMcpBridge import protocol as p
from nvdaMcpBridge.framing import Connection
from nvdaMcpBridge.session import Session, SessionConfig, TeardownReason
from nvdaMcpBridge.transcript import TranscriptLog

NVDA_VERSION = "2026.1.0"


@dataclass
class Ran:
	reason: str
	responses: list[dict[str, Any]]
	source: FakeSpeechSource
	swapper: FakeSynthSwapper
	sender: FakeGestureSender
	transcript_path: Path


def run_session(
	tmp_path: Path,
	requests: list[dict[str, Any]],
	*,
	clock: FakeClock | None = None,
	swapper: FakeSynthSwapper | None = None,
	sender: FakeGestureSender | None = None,
	config: SessionConfig | None = None,
	on_empty: str = "eof",
	prepare: Callable[[FakeSpeechSource], None] | None = None,
) -> Ran:
	clock = clock or FakeClock()
	source = FakeSpeechSource(clock)
	swapper = swapper or FakeSynthSwapper()
	sender = sender or FakeGestureSender()
	if prepare is not None:
		prepare(source)
	transport = FakeTransport.scripted(requests, clock=clock, on_empty=on_empty)
	transcript = TranscriptLog(tmp_path / "session.log", timestamp=lambda: "T")
	session = Session(
		Connection(transport),
		source,
		swapper,
		sender,
		clock,
		transcript,
		nvda_version=NVDA_VERSION,
		config=config,
	)
	reason = session.run()
	return Ran(reason, transport.responses(), source, swapper, sender, tmp_path / "session.log")


def _hello(mode: str = "silent", version: int = p.PROTOCOL_VERSION) -> dict[str, Any]:
	return {"id": 1, "cmd": "hello", "params": {"mode": mode, "protocolVersion": version}}


# -- handshake ----------------------------------------------------------------


def test_silent_handshake_swaps_synth_and_reports_state(tmp_path: Path) -> None:
	ran = run_session(tmp_path, [_hello("silent"), {"id": 2, "cmd": "bye"}])
	hello = ran.responses[0]
	assert hello["id"] == 1
	assert hello["result"] == {
		"protocolVersion": 1,
		"nvdaVersion": NVDA_VERSION,
		"mode": "silent",
		"synth": "espeak",
		"logPath": str(ran.transcript_path),
	}
	assert ran.swapper.swap_count == 1
	assert ran.source.started_mode == "silent"
	assert ran.reason == TeardownReason.CLIENT_BYE


def test_live_handshake_does_not_touch_the_synth(tmp_path: Path) -> None:
	ran = run_session(tmp_path, [_hello("live"), {"id": 2, "cmd": "bye"}])
	assert ran.swapper.swap_count == 0
	assert ran.source.started_mode == "live"
	assert ran.reason == TeardownReason.CLIENT_BYE


def test_protocol_version_mismatch_is_rejected_before_any_swap(tmp_path: Path) -> None:
	ran = run_session(tmp_path, [_hello("silent", version=99)])
	assert ran.reason == TeardownReason.PROTOCOL_ERROR
	assert "protocol version mismatch" in ran.responses[0]["error"]["message"]
	assert ran.swapper.swap_count == 0


def test_unknown_mode_is_rejected(tmp_path: Path) -> None:
	ran = run_session(tmp_path, [_hello("shouting")])
	assert ran.reason == TeardownReason.PROTOCOL_ERROR
	assert "unknown capture mode" in ran.responses[0]["error"]["message"]


def test_first_message_must_be_hello(tmp_path: Path) -> None:
	ran = run_session(tmp_path, [{"id": 1, "cmd": "ping"}])
	assert ran.reason == TeardownReason.PROTOCOL_ERROR
	assert "expected 'hello' first" in ran.responses[0]["error"]["message"]


def test_second_hello_is_rejected(tmp_path: Path) -> None:
	ran = run_session(tmp_path, [_hello("live"), _hello("live"), {"id": 3, "cmd": "bye"}])
	assert ran.responses[1]["error"]["message"].startswith("already connected")


# -- teardown always restores -------------------------------------------------


def test_bye_restores_synth_and_closes_transcript(tmp_path: Path) -> None:
	ran = run_session(tmp_path, [_hello("silent"), {"id": 2, "cmd": "bye"}])
	assert ran.swapper.restore_count == 1
	assert ran.swapper.swapped is False
	log = ran.transcript_path.read_text(encoding="utf-8")
	assert "SYNTH RESTORE -> espeak" in log
	assert "SESSION CLOSE reason=client-bye" in log


def test_client_disconnect_still_restores_synth(tmp_path: Path) -> None:
	# No bye; the transport hits EOF straight after the handshake.
	ran = run_session(tmp_path, [_hello("silent")])
	assert ran.reason == TeardownReason.CLIENT_CLOSED
	assert ran.swapper.restore_count == 1
	assert ran.swapper.swapped is False


def test_restore_failure_is_contained_and_still_logged(tmp_path: Path) -> None:
	swapper = FakeSynthSwapper(raise_on_restore=True)
	ran = run_session(tmp_path, [_hello("silent"), {"id": 2, "cmd": "bye"}], swapper=swapper)
	# run() must not raise; the restore was attempted and the failure noted.
	assert ran.reason == TeardownReason.CLIENT_BYE
	assert swapper.restore_count == 1
	assert "synth restore raised" in ran.transcript_path.read_text(encoding="utf-8")


# -- timeouts -----------------------------------------------------------------


def test_heartbeat_timeout_when_client_goes_silent(tmp_path: Path) -> None:
	clock = FakeClock()
	ran = run_session(
		tmp_path,
		[_hello("silent")],
		clock=clock,
		config=SessionConfig(heartbeat_timeout=30.0, inactivity_timeout=120.0),
		on_empty="timeout",
	)
	assert ran.reason == TeardownReason.HEARTBEAT_TIMEOUT
	assert ran.swapper.restore_count == 1


def test_inactivity_timeout_fires_even_though_pings_keep_heartbeat_alive(tmp_path: Path) -> None:
	# Heartbeat is effectively disabled; a ping refreshes the heartbeat but not
	# the command-activity clock, so inactivity must still fire.
	clock = FakeClock()
	config = SessionConfig(heartbeat_timeout=10_000.0, inactivity_timeout=10.0)
	from fakes import TIMEOUT_EVENT

	transport = FakeTransport(
		[
			p.encode_message(_hello("live")),
			TIMEOUT_EVENT,  # t=+4
			p.encode_message({"id": 2, "cmd": "ping"}),  # refreshes heartbeat only
			TIMEOUT_EVENT,  # t=+8
		],
		clock=clock,
		on_empty="timeout",
		timeout_advance=4.0,
	)
	transcript = TranscriptLog(tmp_path / "session.log", timestamp=lambda: "T")
	session = Session(
		Connection(transport),
		FakeSpeechSource(clock),
		FakeSynthSwapper(),
		FakeGestureSender(),
		clock,
		transcript,
		nvda_version=NVDA_VERSION,
		config=config,
	)
	reason = session.run()
	assert reason == TeardownReason.INACTIVITY_TIMEOUT
	# The ping was answered before inactivity closed the session.
	acks = [r for r in transport.responses() if r.get("result") == {"ok": True}]
	assert acks


# -- command dispatch ---------------------------------------------------------


def test_press_gesture_emulates_each_and_logs_them(tmp_path: Path) -> None:
	ran = run_session(
		tmp_path,
		[
			_hello("live"),
			{"id": 2, "cmd": "pressGesture", "params": {"gestures": ["NVDA+f7", "downArrow"]}},
			{"id": 3, "cmd": "bye"},
		],
	)
	assert ran.sender.sent == ["NVDA+f7", "downArrow"]
	assert ran.responses[1]["result"] == {"ok": True}
	log = ran.transcript_path.read_text(encoding="utf-8")
	assert "GESTURE NVDA+f7" in log and "GESTURE downArrow" in log


def test_bad_gesture_reports_error_after_sending_the_good_ones(tmp_path: Path) -> None:
	sender = FakeGestureSender(invalid={"bogus+key"})
	ran = run_session(
		tmp_path,
		[
			_hello("live"),
			{"id": 2, "cmd": "pressGesture", "params": {"gestures": ["NVDA+f7", "bogus+key"]}},
			{"id": 3, "cmd": "bye"},
		],
		sender=sender,
	)
	assert ran.sender.sent == ["NVDA+f7"]
	assert "bad gesture 'bogus+key'" in ran.responses[1]["error"]["message"]


def test_speech_reads_reflect_the_buffer(tmp_path: Path) -> None:
	def prepare(source: FakeSpeechSource) -> None:
		source.emit_speech("Find")  # index 1
		source.emit_speech("dialog")  # index 2

	ran = run_session(
		tmp_path,
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


def test_wait_for_speech_finds_existing_text(tmp_path: Path) -> None:
	ran = run_session(
		tmp_path,
		[
			_hello("live"),
			{"id": 2, "cmd": "waitForSpeech", "params": {"text": "ready", "timeout": 1}},
			{"id": 3, "cmd": "bye"},
		],
		prepare=lambda s: s.emit_speech("system ready"),
	)
	assert ran.responses[1]["result"] == {"found": True, "index": 1, "text": "system ready"}


def test_wait_for_speech_to_finish_true_in_live_mode(tmp_path: Path) -> None:
	ran = run_session(
		tmp_path,
		[
			_hello("live"),
			{"id": 2, "cmd": "waitForSpeechToFinish", "params": {"timeout": 5}},
			{"id": 3, "cmd": "bye"},
		],
		prepare=lambda s: s.emit_speech("talking"),
	)
	assert ran.responses[1]["result"] == {"finished": True}


def test_get_braille_reads_the_braille_buffer(tmp_path: Path) -> None:
	ran = run_session(
		tmp_path,
		[
			_hello("live"),
			{"id": 2, "cmd": "getBraille", "params": {"sinceIndex": 1}},
			{"id": 3, "cmd": "bye"},
		],
		prepare=lambda s: s.emit_braille("brl text"),
	)
	assert ran.responses[1]["result"] == {"text": "brl text", "fromIndex": 1, "toIndex": 2}


def test_unknown_command_is_reported(tmp_path: Path) -> None:
	ran = run_session(
		tmp_path,
		[_hello("live"), {"id": 2, "cmd": "teleport"}, {"id": 3, "cmd": "bye"}],
	)
	assert "unknown command 'teleport'" in ran.responses[1]["error"]["message"]


def test_introspection_commands_report_not_yet_supported(tmp_path: Path) -> None:
	ran = run_session(
		tmp_path,
		[_hello("live"), {"id": 2, "cmd": "getState"}, {"id": 3, "cmd": "bye"}],
	)
	assert "not supported by this bridge build" in ran.responses[1]["error"]["message"]


def test_malformed_frame_is_reported_and_the_loop_continues(tmp_path: Path) -> None:
	# A frame missing the required 'cmd' after a good handshake.
	ran = run_session(
		tmp_path,
		[_hello("live"), {"id": 2}, {"id": 3, "cmd": "ping"}, {"id": 4, "cmd": "bye"}],
	)
	assert "malformed request" in ran.responses[1]["error"]["message"]
	# The session kept going and answered the following ping.
	assert ran.responses[2] == {"id": 3, "result": {"ok": True}, "error": None}
	assert ran.reason == TeardownReason.CLIENT_BYE
