# nvda-mcp shared wire protocol.
# Copyright (C) 2026 Marlon Brandao de Sousa.
# This file is covered by the GNU General Public License.
# See the file COPYING.txt for more details.
#
# CANONICAL SOURCE. This module is shared *verbatim* by two very different
# hosts:
#
#   * the MCP server (desktop CPython, may also depend on pydantic/mcp), and
#   * the NVDA bridge addon (NVDA's embedded CPython, no third-party deps,
#     shared ``sys.modules`` with every other installed addon).
#
# It must therefore stay **stdlib-only** and have no import side effects. The
# addon build (scons) copies this file into the addon package; the server
# depends on it as an installable package. Because both sides run the exact
# same bytes, the wire contract cannot drift. It is unit-tested once, under
# desktop Python, in ``shared/tests/test_protocol.py``.

from __future__ import annotations

import dataclasses
import enum
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Final, TypeVar, Union, cast, get_args, get_origin, get_type_hints

_T = TypeVar("_T")


def _empty_dict() -> dict[str, Any]:
	return {}


__all__ = [
	"PROTOCOL_VERSION",
	"DEFAULT_PORT",
	"CaptureMode",
	"Command",
	"ValidationError",
	"from_dict",
	"to_dict",
	"encode_message",
	"decode_message",
	"Request",
	"ErrorInfo",
	"Response",
	"HelloParams",
	"HelloResult",
	"EchoParams",
	"EchoResult",
	"PressGestureParams",
	"GetSpeechParams",
	"SpeechResult",
	"LastSpeechResult",
	"NextIndexResult",
	"WaitForSpeechParams",
	"WaitForSpeechResult",
	"WaitToFinishParams",
	"WaitToFinishResult",
	"GetBrailleParams",
	"BrailleResult",
	"FocusInfoResult",
	"StateResult",
	"GetConfigParams",
	"SetConfigParams",
	"ConfigResult",
	"AckResult",
]


# --- Constants ---------------------------------------------------------------

#: Bumped on any incompatible change to the wire contract. The ``hello``
#: handshake rejects a mismatched bridge/server pair with a clear error.
PROTOCOL_VERSION: Final = 1

#: Default loopback TCP port the bridge listens on.
DEFAULT_PORT: Final = 8765


class CaptureMode(StrEnum):
	"""Speech-capture modes, chosen per session at ``hello`` time.

	A ``StrEnum`` so members *are* ``str`` — they serialize to plain JSON and
	compare equal to their wire value — while still giving us a closed set that
	:func:`from_dict` validates (an unknown mode raises, it is not silently
	accepted).
	"""

	#: Bundled spy synth replaces the real synth for the session. Deterministic.
	SILENT = "silent"
	#: Hook ``pre_speechQueued``; the real synth keeps talking.
	LIVE = "live"


class Command(StrEnum):
	"""Wire command names (v1).

	``StrEnum`` members double as their wire strings, so dispatch tables can be
	keyed by ``Command`` yet looked up with a raw ``str`` from the wire.
	"""

	HELLO = "hello"
	PING = "ping"
	ECHO = "echo"
	PRESS_GESTURE = "pressGesture"
	GET_SPEECH = "getSpeech"
	GET_LAST_SPEECH = "getLastSpeech"
	GET_NEXT_SPEECH_INDEX = "getNextSpeechIndex"
	WAIT_FOR_SPEECH = "waitForSpeech"
	WAIT_FOR_SPEECH_TO_FINISH = "waitForSpeechToFinish"
	GET_BRAILLE = "getBraille"
	GET_FOCUS_INFO = "getFocusInfo"
	GET_STATE = "getState"
	GET_CONFIG = "getConfig"
	SET_CONFIG = "setConfig"
	BYE = "bye"


# --- Generic validator -------------------------------------------------------


class ValidationError(ValueError):
	"""Raised by :func:`from_dict` when a payload does not match a dataclass.

	The message names the offending field path so wire faults are diagnosable
	from a log line alone.
	"""


_NONE_TYPE: Final = type(None)


def _union_args(tp: object) -> tuple[Any, ...] | None:
	"""Return the members of ``tp`` if it is a Union / ``X | Y``, else None."""
	origin = get_origin(tp)
	# ``typing.Union[...]`` reports ``typing.Union`` as origin; the PEP 604
	# ``X | Y`` form reports ``types.UnionType``. Both expose members via
	# ``get_args``.
	if origin is Union:
		return get_args(tp)
	# ``types.UnionType`` (3.10+) is not ``typing.Union`` but ``get_origin``
	# returns it for ``int | str``.
	if origin is not None and origin.__class__.__name__ == "UnionType":
		return get_args(tp)
	if type(tp).__name__ == "UnionType":  # bare ``int | None`` value
		return get_args(tp)
	return None


def _coerce(expected: Any, value: Any, path: str) -> Any:
	"""Validate/convert ``value`` against ``expected`` type, or raise."""
	if expected is Any or expected is object:
		return value

	union = _union_args(expected)
	if union is not None:
		if value is None and _NONE_TYPE in union:
			return None
		errors: list[str] = []
		for arg in union:
			if arg is _NONE_TYPE:
				continue
			try:
				return _coerce(arg, value, path)
			except ValidationError as exc:
				errors.append(str(exc))
		raise ValidationError(f"{path}: value {value!r} matched none of {union}: {'; '.join(errors)}")

	origin = get_origin(expected)
	if origin in (list, tuple):
		if not isinstance(value, list):
			raise ValidationError(f"{path}: expected a list, got {type(value).__name__}")
		items = cast("list[Any]", value)
		(elem_type,) = get_args(expected) or (Any,)
		return [_coerce(elem_type, item, f"{path}[{i}]") for i, item in enumerate(items)]
	if origin is dict:
		if not isinstance(value, Mapping):
			raise ValidationError(f"{path}: expected an object, got {type(value).__name__}")
		mapping = cast("Mapping[Any, Any]", value)
		key_type, val_type = get_args(expected) or (Any, Any)
		return {
			_coerce(key_type, k, f"{path}.<key>"): _coerce(val_type, v, f"{path}.{k}")
			for k, v in mapping.items()
		}

	if isinstance(expected, type) and dataclasses.is_dataclass(expected):
		if not isinstance(value, Mapping):
			raise ValidationError(f"{path}: expected an object, got {type(value).__name__}")
		nested = cast("Mapping[str, Any]", value)
		return from_dict(expected, nested)

	# Enums (incl. ``StrEnum``): coerce the wire value to a member, or reject a
	# value outside the closed set with a clear message.
	if isinstance(expected, type) and issubclass(expected, enum.Enum):
		try:
			return expected(value)
		except ValueError as exc:
			raise ValidationError(f"{path}: {value!r} is not a valid {expected.__name__}") from exc

	# Scalars. ``bool`` is a subclass of ``int`` in Python; keep them distinct
	# on the wire so a stray ``true`` is never silently read as ``1``.
	if expected is bool:
		if isinstance(value, bool):
			return value
		raise ValidationError(f"{path}: expected bool, got {type(value).__name__}")
	if expected is int:
		if isinstance(value, bool) or not isinstance(value, int):
			raise ValidationError(f"{path}: expected int, got {type(value).__name__}")
		return value
	if expected is float:
		if isinstance(value, bool) or not isinstance(value, (int, float)):
			raise ValidationError(f"{path}: expected number, got {type(value).__name__}")
		return float(value)
	if expected is str:
		if not isinstance(value, str):
			raise ValidationError(f"{path}: expected str, got {type(value).__name__}")
		return value

	if isinstance(expected, type):
		if isinstance(value, expected):
			return value
		raise ValidationError(f"{path}: expected {expected.__name__}, got {type(value).__name__}")

	# Unknown typing construct: accept rather than reject, so the contract can
	# grow without this validator becoming a bottleneck.
	return value


def from_dict(cls: type[_T], data: Mapping[str, Any]) -> _T:
	"""Build a dataclass instance of ``cls`` from ``data``, validating types.

	Walks ``typing.get_type_hints`` for ``cls`` and coerces each field,
	recursing into nested dataclasses, ``list[...]``, ``dict[...]`` and
	Optionals. Missing required fields and type mismatches raise
	:class:`ValidationError` naming the field path. Extra keys are ignored so
	an older peer tolerates a newer one adding fields.

	``data`` is trusted to be a mapping; every wire entry point
	(:func:`decode_message` and the nested-dataclass branch of ``_coerce``)
	guarantees that before calling here.
	"""
	if not dataclasses.is_dataclass(cls):
		raise ValidationError(f"{getattr(cls, '__name__', cls)!r} is not a dataclass")

	hints = get_type_hints(cls)
	kwargs: dict[str, Any] = {}
	for f in dataclasses.fields(cls):
		if f.name not in data:
			has_default = f.default is not dataclasses.MISSING or f.default_factory is not dataclasses.MISSING
			if has_default:
				continue
			raise ValidationError(f"{cls.__name__}: missing required field {f.name!r}")
		kwargs[f.name] = _coerce(hints[f.name], data[f.name], f"{cls.__name__}.{f.name}")
	return cls(**kwargs)


def to_dict(obj: Any) -> dict[str, Any]:
	"""Serialize a dataclass instance to a plain ``dict`` (recursively)."""
	if not dataclasses.is_dataclass(obj) or isinstance(obj, type):
		raise ValidationError(f"to_dict expects a dataclass instance, got {type(obj).__name__}")
	return dataclasses.asdict(obj)


# --- JSON-lines framing ------------------------------------------------------


def encode_message(obj: Any) -> bytes:
	"""Encode a dataclass (or plain dict) as one UTF-8 JSON line (``\\n``)."""
	payload: Any = to_dict(obj) if dataclasses.is_dataclass(obj) and not isinstance(obj, type) else obj
	return (json.dumps(payload, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def decode_message(line: bytes | str) -> dict[str, Any]:
	"""Decode one JSON line into a dict, raising :class:`ValidationError`."""
	text = line.decode("utf-8") if isinstance(line, bytes) else line
	try:
		parsed: Any = json.loads(text)
	except (ValueError, UnicodeDecodeError) as exc:
		raise ValidationError(f"malformed JSON line: {exc}") from exc
	if not isinstance(parsed, dict):
		raise ValidationError(f"expected a JSON object, got {type(parsed).__name__}")
	return cast("dict[str, Any]", parsed)


# --- Envelope ----------------------------------------------------------------


@dataclass
class Request:
	"""A client→bridge command frame."""

	id: int
	cmd: str
	params: dict[str, Any] = field(default_factory=_empty_dict)


@dataclass
class ErrorInfo:
	message: str


@dataclass
class Response:
	"""A bridge→client reply frame. Exactly one of ``result``/``error`` is set."""

	id: int
	result: Any = None
	error: ErrorInfo | None = None


# --- Command params / results ------------------------------------------------


@dataclass
class HelloParams:
	mode: CaptureMode
	protocolVersion: int


@dataclass
class HelloResult:
	protocolVersion: int
	nvdaVersion: str
	mode: CaptureMode
	synth: str
	logPath: str


@dataclass
class EchoParams:
	"""Diagnostic round-trip: whatever ``payload`` is sent comes back unchanged.

	``payload`` is ``Any`` on purpose — echo exists to prove the *whole* stack
	(encode → frame → decode → validate → dispatch → re-encode) survives arbitrary
	JSON: unicode, nesting, floats, long strings. No other command exercises that
	end to end.
	"""

	payload: Any


@dataclass
class EchoResult:
	payload: Any


@dataclass
class PressGestureParams:
	#: NVDA gesture ids, pressed in order, blocking until each is processed.
	gestures: list[str]


@dataclass
class GetSpeechParams:
	sinceIndex: int


@dataclass
class SpeechResult:
	#: Captured speech sequences joined into one string.
	text: str
	#: Half-open index range ``[fromIndex, toIndex)`` the text covers.
	fromIndex: int
	toIndex: int


@dataclass
class LastSpeechResult:
	text: str
	index: int


@dataclass
class NextIndexResult:
	#: The index the next captured speech sequence will occupy.
	index: int


@dataclass
class WaitForSpeechParams:
	text: str
	afterIndex: int | None = None
	timeout: float = 5.0


@dataclass
class WaitForSpeechResult:
	found: bool
	#: Index of the matching sequence, or the next index if not found.
	index: int
	text: str


@dataclass
class WaitToFinishParams:
	timeout: float = 5.0


@dataclass
class WaitToFinishResult:
	finished: bool


@dataclass
class GetBrailleParams:
	sinceIndex: int


@dataclass
class BrailleResult:
	text: str
	fromIndex: int
	toIndex: int


@dataclass
class FocusInfoResult:
	name: str
	role: str
	states: list[str]
	value: str | None
	appModule: str | None


@dataclass
class StateResult:
	"""Queryable NVDA state that may be signalled by sound rather than speech.

	Diff two snapshots across a gesture to assert a toggle (e.g. NVDA+space
	flipping ``browseMode`` between ``"browse"`` and ``"focus"``).
	"""

	#: ``"browse"`` / ``"focus"`` from the focus object's
	#: ``treeInterceptor.passThrough``; ``None`` when there is no browse document.
	browseMode: str | None
	#: ``"talk"`` / ``"beeps"`` / ``"off"`` / ``"onDemand"``.
	speechMode: str
	sleepMode: bool
	inputHelp: bool


@dataclass
class GetConfigParams:
	keyPath: list[str]


@dataclass
class SetConfigParams:
	keyPath: list[str]
	value: Any


@dataclass
class ConfigResult:
	value: Any


@dataclass
class AckResult:
	"""Generic acknowledgement for commands with no payload (ping, bye, ...)."""

	ok: bool = True
