# nvdaMcpBridge domain -- Session: the session-lifecycle controller.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# ROLE: controller. Runs one whole bridge session end to end.
# HANDED (by wiring.py): a MessageChannel, a Transcript, a Clock, an
#   AdapterFactory, and a SessionConfig -- ports and config only.
# DRIVES: the SpeechBuffer / BrailleBuffer entities it builds after hello, and
#   the mode-specific AdapterSet the factory returns.
#
# The session is one call to run(): handshake, then a dispatch loop guarded by
# two watchdogs (heartbeat, command-inactivity), then teardown. Teardown owns
# the bridge's non-negotiable invariant (AGENTS.md #3): every exit path restores
# the user's synth, each step individually guarded so no failure can skip the
# restore. run() executes on the caller's thread (session C's accept loop);
# request_teardown() is the only method other threads may call.

from __future__ import annotations

import enum
import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable

from ... import protocol
from ..entities.braille_buffer import BrailleBuffer
from ..entities.speech_buffer import SpeechBuffer
from ..ports.gesture_sender import GestureError
from ..ports.message_channel import ChannelClosed, Timeout

if TYPE_CHECKING:
	from ..ports.adapter_factory import AdapterFactory, AdapterSet
	from ..ports.clock import Clock
	from ..ports.message_channel import MessageChannel
	from ..ports.transcript import Transcript


@dataclass(frozen=True)
class SessionConfig:
	"""Per-session settings wiring hands the controller.

	The watchdog windows are separate on purpose: the heartbeat proves the
	harness PROCESS is alive (any message resets it), while command inactivity
	proves the AGENT is still testing (only a real command -- not a ping --
	resets it). See RFC 0001's session-lifecycle section.
	"""

	nvda_version: str
	heartbeat_timeout: float = 30.0
	inactivity_timeout: float = 120.0


class TeardownReason(enum.Enum):
	"""Why a session ended. A domain-only enum (plain Enum, per AGENTS.md).

	Its value is the human string written to the transcript's SESSION CLOSE line.
	"""

	CLIENT_BYE = "client-bye"
	CHANNEL_CLOSED = "channel-closed"
	HEARTBEAT_TIMEOUT = "heartbeat-timeout"
	INACTIVITY_TIMEOUT = "inactivity-timeout"
	HANDSHAKE_FAILED = "handshake-failed"
	EXTERNAL = "external"


class Session:
	"""Orchestrates a single bridge session from handshake to teardown."""

	def __init__(
		self,
		channel: MessageChannel,
		transcript: Transcript,
		clock: Clock,
		factory: AdapterFactory,
		config: SessionConfig,
	) -> None:
		self._channel = channel
		self._transcript = transcript
		self._clock = clock
		self._factory = factory
		self._config = config

		# Set once hello succeeds; None until then (and after a handshake that
		# never got that far, so teardown skips what was never built).
		self._adapters: AdapterSet | None = None
		self._speech: SpeechBuffer | None = None
		self._braille: BrailleBuffer | None = None
		self._swapped_real: str | None = None

		# Watchdog bookkeeping (monotonic seconds).
		self._last_message_time: float = 0.0
		self._last_command_time: float = 0.0

		# Cross-thread teardown request (request_teardown may come from another
		# thread; the loop honours it at the next wakeup).
		self._external_lock = threading.Lock()
		self._external_reason: TeardownReason | None = None

		self._reason: TeardownReason | None = None
		self._torn_down = False

		self._handlers: dict[str, Callable[[protocol.Request], bool]] = self._build_handlers()

	# -- public API ----------------------------------------------------------

	def run(self) -> None:
		"""Run the whole session on the caller's thread; always tears down."""
		try:
			if self._handshake():
				self._main_loop()
		finally:
			self._teardown()

	def request_teardown(self, reason: TeardownReason) -> None:
		"""Ask the session to end (thread-safe; honoured at the next wakeup).

		Used by session C's plugin ``terminate`` and the panic gesture. The
		first request wins; later ones are ignored.
		"""
		with self._external_lock:
			if self._external_reason is None:
				self._external_reason = reason

	# -- handshake -----------------------------------------------------------

	def _handshake(self) -> bool:
		"""Read the first message; it must be a valid ``hello`` in time.

		Strict on purpose: unlike mid-session garbage, nothing is invested yet,
		so anything that is not a clean hello -- timeout, closed channel,
		garbage, wrong command, bad params, version mismatch -- ends the session
		with HANDSHAKE_FAILED (replying an error first when an id is recoverable).
		"""
		deadline = self._clock.monotonic() + self._config.heartbeat_timeout
		while True:
			if self._external_requested():
				return False
			try:
				raw = self._channel.read_message()
			except ChannelClosed:
				self._reason = TeardownReason.HANDSHAKE_FAILED
				return False
			except protocol.ValidationError:
				# Garbage before hello has no recoverable id to reply to.
				self._reason = TeardownReason.HANDSHAKE_FAILED
				return False
			if isinstance(raw, Timeout):
				if self._clock.monotonic() >= deadline:
					self._reason = TeardownReason.HANDSHAKE_FAILED
					return False
				continue
			return self._process_hello(raw)

	def _process_hello(self, raw: dict[str, Any]) -> bool:
		try:
			request = protocol.from_dict(protocol.Request, raw)
		except protocol.ValidationError:
			self._reply_error(self._extract_id(raw), "handshake: expected a hello request")
			self._reason = TeardownReason.HANDSHAKE_FAILED
			return False
		if request.cmd != protocol.Command.HELLO:
			self._reply_error(request.id, f"handshake: expected hello, got {request.cmd!r}")
			self._reason = TeardownReason.HANDSHAKE_FAILED
			return False
		try:
			params = protocol.from_dict(protocol.HelloParams, request.params)
		except protocol.ValidationError as exc:
			self._reply_error(request.id, f"handshake: invalid hello params: {exc}")
			self._reason = TeardownReason.HANDSHAKE_FAILED
			return False
		if params.protocolVersion != protocol.PROTOCOL_VERSION:
			self._reply_error(
				request.id,
				f"protocol version mismatch: bridge speaks {protocol.PROTOCOL_VERSION}, "
				f"client sent {params.protocolVersion}",
			)
			self._reason = TeardownReason.HANDSHAKE_FAILED
			return False
		self._open_session(request.id, params)
		return True

	def _open_session(self, hello_id: int, params: protocol.HelloParams) -> None:
		self._transcript.open()
		adapters = self._factory.build(params.mode)
		self._adapters = adapters
		silent = params.mode is protocol.CaptureMode.SILENT
		self._speech = SpeechBuffer(self._clock, exact_finish=silent)
		self._braille = BrailleBuffer(self._clock)
		self._speech.set_observer(self._transcript.speech)
		adapters.speech_source.start(self._speech)
		adapters.braille_source.start(self._braille)

		synth = adapters.synth_swapper.current_synth()
		self._transcript.session_opened(params.mode, synth)
		if silent:
			real = adapters.synth_swapper.swap_to_spy()
			self._swapped_real = real
			self._transcript.synth_swapped(real)

		now = self._clock.monotonic()
		self._last_message_time = now
		self._last_command_time = now
		self._reply(
			hello_id,
			protocol.HelloResult(
				protocolVersion=protocol.PROTOCOL_VERSION,
				nvdaVersion=self._config.nvda_version,
				mode=params.mode,
				synth=synth,
				logPath=self._transcript.path,
			),
		)

	# -- main loop + watchdogs ----------------------------------------------

	def _main_loop(self) -> None:
		while True:
			if self._external_requested():
				return
			try:
				raw = self._channel.read_message()
			except ChannelClosed:
				self._reason = TeardownReason.CHANNEL_CLOSED
				return
			except protocol.ValidationError as exc:
				# Bytes arrived (peer is alive) but were unreadable: note it and
				# keep going -- garbage must not kill a session.
				self._transcript.note(f"unreadable message: {exc}")
				self._touch_heartbeat()
				if self._deadline_exceeded():
					return
				continue
			if isinstance(raw, Timeout):
				if self._deadline_exceeded():
					return
				continue
			self._touch_heartbeat()
			if not self._dispatch(raw):
				return
			if self._deadline_exceeded():
				return

	def _touch_heartbeat(self) -> None:
		self._last_message_time = self._clock.monotonic()

	def _deadline_exceeded(self) -> bool:
		now = self._clock.monotonic()
		if now - self._last_message_time >= self._config.heartbeat_timeout:
			self._reason = TeardownReason.HEARTBEAT_TIMEOUT
			return True
		if now - self._last_command_time >= self._config.inactivity_timeout:
			self._reason = TeardownReason.INACTIVITY_TIMEOUT
			return True
		return False

	# -- dispatch ------------------------------------------------------------

	def _dispatch(self, raw: dict[str, Any]) -> bool:
		"""Handle one message. Returns False to end the session (a clean bye)."""
		try:
			request = protocol.from_dict(protocol.Request, raw)
		except protocol.ValidationError as exc:
			self._reply_error(self._extract_id(raw), f"invalid request: {exc}")
			return True
		handler = self._handlers.get(request.cmd)
		if handler is None:
			self._reply_error(request.id, f"unknown command: {request.cmd!r}")
			return True
		# Any real command resets inactivity; a ping proves liveness only.
		if request.cmd != protocol.Command.PING:
			self._last_command_time = self._clock.monotonic()
		try:
			return handler(request)
		except protocol.ValidationError as exc:
			self._reply_error(request.id, f"invalid params: {exc}")
			return True
		except Exception as exc:  # a handler blew up; the session survives it
			self._reply_error(request.id, str(exc))
			return True

	def _build_handlers(self) -> dict[str, Callable[[protocol.Request], bool]]:
		C = protocol.Command
		return {
			C.PING: self._handle_ping,
			C.PRESS_GESTURE: self._handle_press_gesture,
			C.GET_SPEECH: self._handle_get_speech,
			C.GET_LAST_SPEECH: self._handle_get_last_speech,
			C.GET_NEXT_SPEECH_INDEX: self._handle_get_next_index,
			C.WAIT_FOR_SPEECH: self._handle_wait_for_speech,
			C.WAIT_FOR_SPEECH_TO_FINISH: self._handle_wait_to_finish,
			C.GET_BRAILLE: self._handle_get_braille,
			C.BYE: self._handle_bye,
			C.HELLO: self._handle_duplicate_hello,
			C.GET_FOCUS_INFO: self._handle_not_implemented,
			C.GET_STATE: self._handle_not_implemented,
			C.GET_CONFIG: self._handle_not_implemented,
			C.SET_CONFIG: self._handle_not_implemented,
		}

	def _handle_ping(self, request: protocol.Request) -> bool:
		self._reply(request.id, protocol.AckResult())
		return True

	def _handle_press_gesture(self, request: protocol.Request) -> bool:
		params = protocol.from_dict(protocol.PressGestureParams, request.params)
		for gesture_id in params.gestures:
			self._transcript.gesture(gesture_id)
			try:
				self._active_adapters.gesture_sender.press(gesture_id)
			except GestureError as exc:
				self._reply_error(request.id, str(exc))
				return True
		self._reply(request.id, protocol.AckResult())
		return True

	def _handle_get_speech(self, request: protocol.Request) -> bool:
		params = protocol.from_dict(protocol.GetSpeechParams, request.params)
		text, from_index, to_index = self._speech_buffer.get_since(params.sinceIndex)
		self._reply(request.id, protocol.SpeechResult(text=text, fromIndex=from_index, toIndex=to_index))
		return True

	def _handle_get_last_speech(self, request: protocol.Request) -> bool:
		text, index = self._speech_buffer.get_last()
		self._reply(request.id, protocol.LastSpeechResult(text=text, index=index))
		return True

	def _handle_get_next_index(self, request: protocol.Request) -> bool:
		self._reply(request.id, protocol.NextIndexResult(index=self._speech_buffer.next_index()))
		return True

	def _handle_wait_for_speech(self, request: protocol.Request) -> bool:
		params = protocol.from_dict(protocol.WaitForSpeechParams, request.params)
		found, index, text = self._speech_buffer.wait_for(params.text, params.afterIndex, params.timeout)
		self._reply(request.id, protocol.WaitForSpeechResult(found=found, index=index, text=text))
		return True

	def _handle_wait_to_finish(self, request: protocol.Request) -> bool:
		params = protocol.from_dict(protocol.WaitToFinishParams, request.params)
		finished = self._speech_buffer.wait_to_finish(params.timeout)
		self._reply(request.id, protocol.WaitToFinishResult(finished=finished))
		return True

	def _handle_get_braille(self, request: protocol.Request) -> bool:
		params = protocol.from_dict(protocol.GetBrailleParams, request.params)
		text, from_index, to_index = self._braille_buffer.get_since(params.sinceIndex)
		self._reply(request.id, protocol.BrailleResult(text=text, fromIndex=from_index, toIndex=to_index))
		return True

	def _handle_bye(self, request: protocol.Request) -> bool:
		self._reply(request.id, protocol.AckResult())
		self._reason = TeardownReason.CLIENT_BYE
		return False

	def _handle_duplicate_hello(self, request: protocol.Request) -> bool:
		self._reply_error(request.id, "session already established")
		return True

	def _handle_not_implemented(self, request: protocol.Request) -> bool:
		self._reply_error(request.id, f"{request.cmd} is not implemented in this bridge yet")
		return True

	# -- teardown ------------------------------------------------------------

	def _teardown(self) -> None:
		"""Run exactly once, in ``finally``, on every exit path.

		Each step is individually guarded so a failure in one never skips the
		rest -- above all, ``restore()`` is attempted whenever a swapper exists
		(idempotent by contract), and neither a raising transcript nor a raising
		restore can stop the channel from closing.
		"""
		if self._torn_down:
			return
		self._torn_down = True
		reason = self._reason if self._reason is not None else TeardownReason.EXTERNAL
		if self._adapters is not None:
			self._guard(self._adapters.speech_source.stop)
			self._guard(self._adapters.braille_source.stop)
			self._guard(self._adapters.synth_swapper.restore)
		if self._swapped_real is not None:
			real = self._swapped_real
			self._guard(lambda: self._transcript.synth_restored(real))
		self._guard(lambda: self._transcript.session_closed(reason.value))
		self._guard(self._channel.close)

	@staticmethod
	def _guard(action: Callable[[], object]) -> None:
		try:
			action()
		except Exception:
			# Teardown must complete on every path; a failure here is swallowed
			# so the remaining steps (crucially, the synth restore) still run.
			pass

	# -- helpers -------------------------------------------------------------

	@property
	def _active_adapters(self) -> AdapterSet:
		assert self._adapters is not None, "adapters accessed before hello"
		return self._adapters

	@property
	def _speech_buffer(self) -> SpeechBuffer:
		assert self._speech is not None, "speech buffer accessed before hello"
		return self._speech

	@property
	def _braille_buffer(self) -> BrailleBuffer:
		assert self._braille is not None, "braille buffer accessed before hello"
		return self._braille

	def _external_requested(self) -> bool:
		with self._external_lock:
			if self._external_reason is None:
				return False
			self._reason = self._external_reason
			return True

	def _reply(self, request_id: int, result: Any) -> None:
		self._safe_write(protocol.Response(id=request_id, result=result))

	def _reply_error(self, request_id: int | None, message: str) -> None:
		if request_id is None:
			# No id to attribute the error to; the transcript still records it.
			self._transcript.note(f"unattributable error: {message}")
			return
		self._safe_write(protocol.Response(id=request_id, error=protocol.ErrorInfo(message=message)))

	def _safe_write(self, response: protocol.Response) -> None:
		# A dead channel during a reply is caught by the next read (which raises
		# ChannelClosed and tears down), so a failed write here is swallowed
		# rather than crashing the loop before the read can observe the close.
		try:
			self._channel.write(response)
		except Exception:
			pass

	@staticmethod
	def _extract_id(raw: dict[str, Any]) -> int | None:
		candidate = raw.get("id")
		if isinstance(candidate, bool) or not isinstance(candidate, int):
			return None
		return candidate
