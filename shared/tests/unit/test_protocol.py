# Tests for the shared wire protocol. Stdlib + pytest only, desktop Python.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from nvda_mcp_wire import protocol as p


# --- from_dict: happy paths --------------------------------------------------


def test_from_dict_simple_scalars() -> None:
	hp = p.from_dict(p.HelloParams, {"mode": "silent", "protocolVersion": 1})
	assert hp == p.HelloParams(mode=p.CaptureMode.SILENT, protocolVersion=1)


def test_from_dict_applies_defaults_for_missing_optional_fields() -> None:
	w = p.from_dict(p.WaitForSpeechParams, {"text": "hello"})
	assert w == p.WaitForSpeechParams(text="hello", afterIndex=None, timeout=5.0)


def test_from_dict_list_of_str() -> None:
	g = p.from_dict(p.PressGestureParams, {"gestures": ["NVDA+f7", "control+a"]})
	assert g.gestures == ["NVDA+f7", "control+a"]


def test_from_dict_optional_present() -> None:
	w = p.from_dict(p.WaitForSpeechParams, {"text": "x", "afterIndex": 3, "timeout": 2})
	assert w.afterIndex == 3
	# int is widened to float for a float field.
	assert w.timeout == 2.0
	assert isinstance(w.timeout, float)


def test_from_dict_any_field_passes_through() -> None:
	s = p.from_dict(p.SetConfigParams, {"keyPath": ["speech", "synth"], "value": {"a": [1, 2]}})
	assert s.value == {"a": [1, 2]}
	c = p.from_dict(p.ConfigResult, {"value": None})
	assert c.value is None


def test_from_dict_nested_dataclass() -> None:
	@dataclass
	class Outer:
		info: p.ErrorInfo
		count: int

	o = p.from_dict(Outer, {"info": {"message": "boom"}, "count": 2})
	assert o.info == p.ErrorInfo(message="boom")
	assert o.count == 2


def test_from_dict_ignores_extra_keys_for_forward_compat() -> None:
	hp = p.from_dict(p.HelloParams, {"mode": "live", "protocolVersion": 1, "futureField": 99})
	assert hp.mode == "live"


def test_from_dict_dict_field() -> None:
	req = p.from_dict(p.Request, {"id": 1, "cmd": "ping", "params": {"a": 1, "b": "x"}})
	assert req.params == {"a": 1, "b": "x"}


def test_from_dict_request_default_params() -> None:
	req = p.from_dict(p.Request, {"id": 7, "cmd": "ping"})
	assert req.params == {}


# --- from_dict: failure paths ------------------------------------------------


def test_missing_required_field_raises_with_name() -> None:
	with pytest.raises(p.ValidationError, match="protocolVersion"):
		p.from_dict(p.HelloParams, {"mode": "silent"})


def test_wrong_scalar_type_raises_with_path() -> None:
	with pytest.raises(p.ValidationError, match="HelloParams.protocolVersion"):
		p.from_dict(p.HelloParams, {"mode": "silent", "protocolVersion": "one"})


def test_bool_not_accepted_as_int() -> None:
	with pytest.raises(p.ValidationError):
		p.from_dict(p.HelloParams, {"mode": "silent", "protocolVersion": True})


def test_int_not_accepted_as_bool() -> None:
	with pytest.raises(p.ValidationError):
		p.from_dict(p.WaitToFinishResult, {"finished": 1})


def test_list_element_type_checked() -> None:
	with pytest.raises(p.ValidationError, match=r"gestures\[1\]"):
		p.from_dict(p.PressGestureParams, {"gestures": ["ok", 5]})


def test_list_field_rejects_non_list() -> None:
	with pytest.raises(p.ValidationError, match="expected a list"):
		p.from_dict(p.PressGestureParams, {"gestures": "NVDA+f7"})


def test_optional_rejects_wrong_non_none_type() -> None:
	with pytest.raises(p.ValidationError, match="afterIndex"):
		p.from_dict(p.WaitForSpeechParams, {"text": "x", "afterIndex": "nope"})


def test_from_dict_on_non_dataclass_raises() -> None:
	with pytest.raises(p.ValidationError):
		p.from_dict(int, {})  # type: ignore[type-var]


def test_nested_non_mapping_raises() -> None:
	# The real defensive path: a nested dataclass field fed a non-object.
	@dataclass
	class Outer:
		info: p.ErrorInfo

	with pytest.raises(p.ValidationError, match="expected an object"):
		p.from_dict(Outer, {"info": [1, 2, 3]})


# --- to_dict / round trips ---------------------------------------------------


def test_to_dict_round_trips_params() -> None:
	original = p.WaitForSpeechParams(text="done", afterIndex=4, timeout=3.5)
	assert p.from_dict(p.WaitForSpeechParams, p.to_dict(original)) == original


def test_to_dict_recurses_nested() -> None:
	r = p.Response(id=1, error=p.ErrorInfo(message="bad"))
	assert p.to_dict(r) == {"id": 1, "result": None, "error": {"message": "bad"}}


def test_to_dict_rejects_dataclass_type() -> None:
	with pytest.raises(p.ValidationError):
		p.to_dict(p.HelloParams)


def test_response_optional_dataclass_from_dict() -> None:
	resp = p.from_dict(p.Response, {"id": 2, "result": {"ok": True}, "error": None})
	assert resp.result == {"ok": True}
	assert resp.error is None
	resp2 = p.from_dict(p.Response, {"id": 3, "error": {"message": "x"}})
	assert resp2.error == p.ErrorInfo(message="x")


# --- JSON-lines framing ------------------------------------------------------


def test_encode_message_is_single_newline_terminated_line() -> None:
	raw = p.encode_message(p.Request(id=1, cmd="ping"))
	assert raw.endswith(b"\n")
	assert raw.count(b"\n") == 1
	assert isinstance(raw, bytes)


def test_encode_decode_round_trip() -> None:
	raw = p.encode_message(p.HelloParams(mode=p.CaptureMode.SILENT, protocolVersion=1))
	decoded = p.decode_message(raw)
	assert p.from_dict(p.HelloParams, decoded) == p.HelloParams(mode=p.CaptureMode.SILENT, protocolVersion=1)


@pytest.mark.parametrize(
	"payload",
	[
		"olá café \U0001f600",
		{"nested": [1, 2, {"deep": True}], "n": 3.5, "s": "x"},
		[True, None, "mix", 42],
		"x" * 5000,
	],
)
def test_echo_payload_survives_the_full_stack(payload: Any) -> None:
	# encode -> frame -> decode -> validate -> back to the dataclass, byte-exact.
	raw = p.encode_message(p.EchoResult(payload=payload))
	restored = p.from_dict(p.EchoResult, p.decode_message(raw))
	assert restored.payload == payload


def test_encode_non_ascii_preserved() -> None:
	raw = p.encode_message(p.SpeechResult(text="olá café", fromIndex=0, toIndex=1))
	assert "olá café" in raw.decode("utf-8")


def test_encode_plain_dict() -> None:
	raw = p.encode_message({"id": 1, "result": None})
	assert p.decode_message(raw) == {"id": 1, "result": None}


def test_decode_malformed_json_raises() -> None:
	with pytest.raises(p.ValidationError, match="malformed JSON"):
		p.decode_message(b"{not json")


def test_decode_non_object_raises() -> None:
	with pytest.raises(p.ValidationError, match="expected a JSON object"):
		p.decode_message(b"[1, 2, 3]")


def test_decode_accepts_str_and_bytes() -> None:
	assert p.decode_message('{"a": 1}') == {"a": 1}
	assert p.decode_message(b'{"a": 1}') == {"a": 1}


# --- constants / contract ----------------------------------------------------


def test_protocol_version_is_one() -> None:
	assert p.PROTOCOL_VERSION == 1


def test_default_port() -> None:
	assert p.DEFAULT_PORT == 8765


def test_capture_modes() -> None:
	assert {m.value for m in p.CaptureMode} == {"silent", "live"}


def test_from_dict_coerces_str_to_enum_member() -> None:
	hp = p.from_dict(p.HelloParams, {"mode": "live", "protocolVersion": 1})
	assert hp.mode is p.CaptureMode.LIVE
	assert isinstance(hp.mode, p.CaptureMode)


def test_from_dict_rejects_value_outside_the_enum() -> None:
	with pytest.raises(p.ValidationError, match="not a valid CaptureMode"):
		p.from_dict(p.HelloParams, {"mode": "shouting", "protocolVersion": 1})


def test_command_set_matches_plan_v1() -> None:
	expected = {
		"hello",
		"ping",
		"echo",
		"pressGesture",
		"getSpeech",
		"getLastSpeech",
		"getNextSpeechIndex",
		"waitForSpeech",
		"waitForSpeechToFinish",
		"getBraille",
		"getFocusInfo",
		"getState",
		"getConfig",
		"setConfig",
		"announce",
		"bye",
	}
	assert {c.value for c in p.Command} == expected


def test_hello_result_serializes_all_fields() -> None:
	hr = p.HelloResult(
		protocolVersion=1,
		reader=p.ReaderInfo(name="nvda", version="2026.1.0"),
		capabilities=[p.Capability.SPEECH, p.Capability.GESTURES],
		mode=p.CaptureMode.SILENT,
		synth="oneCore",
		logPath=r"C:\x\session.log",
		nvdaLogPath=r"C:\x\nvda-log.log",
	)
	d = p.to_dict(hr)
	assert set(d) == {
		"protocolVersion",
		"reader",
		"capabilities",
		"mode",
		"synth",
		"logPath",
		"nvdaLogPath",
	}
	# The nested ReaderInfo serializes to a plain dict; StrEnum members to strings.
	assert d["reader"] == {"name": "nvda", "version": "2026.1.0"}
	assert d["capabilities"] == ["speech", "gestures"]


def test_hello_result_round_trips_reader_and_capabilities() -> None:
	original = p.HelloResult(
		protocolVersion=1,
		reader=p.ReaderInfo(name="nvda", version="2026.1.0"),
		capabilities=list(p.Capability),
		mode=p.CaptureMode.LIVE,
		synth="oneCore",
		logPath="/x/session.log",
		nvdaLogPath="/x/nvda-log.log",
	)
	restored = p.from_dict(p.HelloResult, p.decode_message(p.encode_message(original)))
	assert restored == original
	assert isinstance(restored.reader, p.ReaderInfo)
	assert all(isinstance(c, p.Capability) for c in restored.capabilities)


def test_capabilities_cover_one_per_command_group() -> None:
	assert {c.value for c in p.Capability} == {
		"speech",
		"braille",
		"gestures",
		"focus",
		"state",
		"config",
		"announce",
	}


def test_from_dict_rejects_unknown_capability() -> None:
	with pytest.raises(p.ValidationError, match="not a valid Capability"):
		p.from_dict(
			p.HelloResult,
			{
				"protocolVersion": 1,
				"reader": {"name": "nvda", "version": "x"},
				"capabilities": ["speech", "telepathy"],
				"mode": "live",
				"synth": "oneCore",
				"logPath": "/x",
				"nvdaLogPath": "/x/nvda-log.log",
			},
		)


# --- LogLevel / hello logLevel ------------------------------------------------


def test_log_levels_match_nvdas_own_valid_values() -> None:
	assert {m.value for m in p.LogLevel} == {"debug", "io", "debugwarning", "info"}


def test_hello_params_default_log_level_is_none() -> None:
	hp = p.from_dict(p.HelloParams, {"mode": "silent", "protocolVersion": 1})
	assert hp.logLevel is None


def test_hello_params_accepts_a_requested_log_level() -> None:
	hp = p.from_dict(p.HelloParams, {"mode": "silent", "protocolVersion": 1, "logLevel": "debug"})
	assert hp.logLevel is p.LogLevel.DEBUG


def test_hello_params_rejects_an_unknown_log_level() -> None:
	with pytest.raises(p.ValidationError, match="not a valid LogLevel"):
		p.from_dict(p.HelloParams, {"mode": "silent", "protocolVersion": 1, "logLevel": "verbose"})


def test_command_shapes_cover_every_command() -> None:
	# The whole point of COMMAND_SHAPES: no command can exist without declared
	# param/result types, so the generated schema can never miss one.
	assert set(p.COMMAND_SHAPES) == set(p.Command)
	for command, shape in p.COMMAND_SHAPES.items():
		assert shape.result is not None, command
		# A declared params type is always a dataclass; None means "no params".
		if shape.params is not None:
			assert isinstance(shape.params, type)


@pytest.mark.parametrize(
	"cls,payload",
	[
		(p.GetSpeechParams, {"sinceIndex": 0}),
		(p.GetBrailleParams, {"sinceIndex": 3}),
		(p.WaitToFinishParams, {}),
		(p.GetConfigParams, {"keyPath": ["speech", "synth"]}),
		(
			p.FocusInfoResult,
			{"name": "OK", "role": "button", "states": [], "value": None, "appModule": "notepad"},
		),
		(
			p.StateResult,
			{"browseMode": "focus", "speechMode": "talk", "sleepMode": False, "inputHelp": False},
		),
		(p.StateResult, {"browseMode": None, "speechMode": "beeps", "sleepMode": True, "inputHelp": False}),
	],
)
def test_representative_payloads_validate(cls: type[Any], payload: dict[str, Any]) -> None:
	obj = p.from_dict(cls, payload)
	# Everything that validated must round-trip back to a superset of its input.
	out = p.to_dict(obj)
	for k, v in payload.items():
		assert out[k] == v
