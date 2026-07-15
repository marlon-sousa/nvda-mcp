# nvdaMcpBridge domain -- Session: the session orchestrator.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# ROLE: THE controller. One accepted connection == one Session, run end to end.
# CONSTRUCTED BY: wiring.py, which hands it the ports below and nothing else.
# DEPENDS ON (all ports): MessageChannel (its only I/O), Clock (deadlines),
#   Transcript (the human-readable record), AdapterFactory (see mode, below).
# DRIVES (entities): SpeechBuffer / BrailleBuffer, reached via the SpeechSource
#   port the factory builds.
#
# What it orchestrates:
#   1. handshake  -- read `hello`, check protocol version + mode.
#   2. build      -- mode is ONLY known after `hello`, so adapters are not
#                    injected pre-built: the AdapterFactory port is, and we ask
#                    it to build(mode). No configure-after-construction.
#   3. dispatch   -- one handler per wire command, answering from the entities.
#   4. watchdogs  -- heartbeat (no traffic at all -> harness died) and
#                    command-inactivity (pings arrive but nobody is testing;
#                    a ping proves the process lives, not that anyone is using
#                    it). Either expiring ends the session.
#   5. teardown   -- ALWAYS restores the synth, on every path. This is the one
#                    guarantee the whole design exists to make.

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable

from ... import protocol as p
from ..ports.message_channel import ChannelClosed, Timeout

if TYPE_CHECKING:
	from ..ports.adapter_factory import AdapterFactory
	from ..ports.clock import Clock
	from ..ports.gesture_sender import GestureSender
	from ..ports.message_channel import MessageChannel
	from ..ports.speech_source import SpeechSource
	from ..ports.synth_swapper import SynthSwapper
	from ..ports.transcript import Transcript


class TeardownReason(enum.Enum):
	"""Why a session ended -- recorded in the transcript, useful in diagnosis."""

	CLIENT_BYE = "client-bye"
	CLIENT_CLOSED = "client-closed"
	TRANSPORT_ERROR = "transport-error"
	HEARTBEAT_TIMEOUT = "heartbeat-timeout"
	INACTIVITY_TIMEOUT = "inactivity-timeout"
	PROTOCOL_ERROR = "protocol-error"
	SERVER_SHUTDOWN = "server-shutdown"


@dataclass
class SessionConfig:
	heartbeat_timeout: float = 30.0
	inactivity_timeout: float = 120.0


class _WireError(Exception):
	"""A per-command failure reported to the client as an ``error`` response."""


class Session:
	"""Runs one bridge session over a message channel until teardown."""

	def __init__(
		self,
		channel: MessageChannel,
		clock: Clock,
		transcript: Transcript,
		factory: AdapterFactory,
		*,
		nvda_version: str,
		config: SessionConfig | None = None,
	) -> None:
		self._channel = channel
		self._clock = clock
		self._transcript = transcript
		self._factory = factory
		self._nvda_version = nvda_version
		self._config = config or SessionConfig()

		# Bound once the handshake reveals the mode (see _start_session).
		self._speech: SpeechSource | None = None
		self._synth: SynthSwapper | None = None
		self._gestures: GestureSender | None = None

		self._mode: p.CaptureMode | None = None
		self._started = False
		now = clock.monotonic()
		self._last_heartbeat = now
		self._last_command = now
		self._handlers: dict[str, Callable[[p.Request], Any]] = self._build_handlers()

	# -- lifecycle ------------------------------------------------------------

	def run(self) -> TeardownReason:
		"""Drive the session to completion; returns the :class:`TeardownReason`."""
		reason = TeardownReason.CLIENT_CLOSED
		try:
			if not self._handshake():
				return TeardownReason.PROTOCOL_ERROR
			reason = self._command_loop()
		except ChannelClosed:
			reason = TeardownReason.CLIENT_CLOSED
		except OSError:
			reason = TeardownReason.TRANSPORT_ERROR
		finally:
			self._teardown(reason)
		return reason

	def _handshake(self) -> bool:
		"""Read and validate the first frame; start capture on success.

		Returns ``False`` (after sending a clear error) if the first message is
		not a well-formed ``hello`` with a matching protocol version and a known
		mode, or if the client goes away / stays silent past the heartbeat.
		"""
		message = self._await_message()
		if message is None:
			return False
		req = self._parse_request(message)
		if req is None:
			return False
		if req.cmd != p.Command.HELLO:
			self._send_error(req.id, f"expected {p.Command.HELLO.value!r} first, got {req.cmd!r}")
			return False
		try:
			hello = p.from_dict(p.HelloParams, req.params)
		except p.ValidationError as exc:
			self._send_error(req.id, f"malformed hello: {exc}")
			return False
		if hello.protocolVersion != p.PROTOCOL_VERSION:
			self._send_error(
				req.id,
				f"protocol version mismatch: bridge speaks {p.PROTOCOL_VERSION}, "
				f"client sent {hello.protocolVersion}",
			)
			return False

		self._start_session(hello.mode)
		assert self._synth is not None
		self._channel.write(
			p.Response(
				id=req.id,
				result=p.HelloResult(
					protocolVersion=p.PROTOCOL_VERSION,
					nvdaVersion=self._nvda_version,
					mode=hello.mode,
					synth=self._synth.real_synth_name,
					logPath=self._transcript.path,
				),
			)
		)
		return True

	def _start_session(self, mode: p.CaptureMode) -> None:
		self._mode = mode
		adapters = self._factory.build(mode)
		self._speech = adapters.speech_source
		self._synth = adapters.synth_swapper
		self._gestures = adapters.gesture_sender

		self._transcript.open()
		# From here on teardown must run in full (close the log, restore the
		# synth), so mark started before any step that could fail.
		self._started = True
		if mode == p.CaptureMode.SILENT:
			self._synth.swap_in()
			self._transcript.synth_swapped(self._synth.real_synth_name)
		self._speech.start()
		self._speech.speech.set_observer(self._transcript.speech)
		self._transcript.session_opened(mode.value, self._synth.real_synth_name)
		now = self._clock.monotonic()
		self._last_heartbeat = now
		self._last_command = now

	def _command_loop(self) -> TeardownReason:
		while True:
			message = self._read_or_report()
			if message is None:
				continue
			if isinstance(message, Timeout):
				expired = self._check_deadlines()
				if expired is not None:
					return expired
				continue
			self._last_heartbeat = self._clock.monotonic()
			req = self._parse_request(message)
			if req is None:
				continue
			if req.cmd == p.Command.BYE:
				self._send_result(req.id, p.AckResult())
				return TeardownReason.CLIENT_BYE
			if req.cmd != p.Command.PING:
				self._last_command = self._clock.monotonic()
			self._dispatch(req)

	def _check_deadlines(self) -> TeardownReason | None:
		now = self._clock.monotonic()
		if now - self._last_heartbeat >= self._config.heartbeat_timeout:
			return TeardownReason.HEARTBEAT_TIMEOUT
		if now - self._last_command >= self._config.inactivity_timeout:
			return TeardownReason.INACTIVITY_TIMEOUT
		return None

	def _teardown(self, reason: TeardownReason) -> None:
		"""Best-effort cleanup that always attempts synth restore and never raises.

		The synth restore is the one guarantee this whole design exists to make
		(a crashed harness must not leave a blind user muted), so it is
		attempted on every path and its failure is contained rather than allowed
		to abort teardown or propagate out of :meth:`run`.
		"""
		try:
			if self._started and self._speech is not None:
				self._speech.speech.set_observer(None)
				self._speech.stop()
		except Exception:  # noqa: BLE001 - cleanup must not mask restoration
			pass
		if self._synth is None:
			# Never got past the handshake; nothing was swapped.
			self._close_channel()
			return
		was_swapped = self._synth.swapped
		try:
			self._synth.restore()  # idempotent; no-op if never swapped
		except Exception:  # noqa: BLE001 - nothing more we can do here
			if self._started:
				self._transcript.note("synth restore raised; see NVDA log")
		else:
			if was_swapped and self._started:
				self._transcript.synth_restored(self._synth.real_synth_name)
		if self._started:
			self._transcript.session_closed(reason.value)
		self._close_channel()

	def _close_channel(self) -> None:
		try:
			self._channel.close()
		except OSError:
			pass

	# -- reading helpers ------------------------------------------------------

	def _read_or_report(self) -> dict[str, Any] | Timeout | None:
		"""Read one message, turning an unreadable one into an error response.

		A client that sends garbage bytes must not take the session down with it
		(and must certainly not skip the synth restore), so an unreadable frame
		is reported and the loop continues. ``None`` means "reported, carry on".
		"""
		try:
			return self._channel.read_message()
		except p.ValidationError as exc:
			# Unparseable: there is no id to correlate against.
			self._send_error(0, f"unreadable message: {exc}")
			return None

	def _await_message(self) -> dict[str, Any] | None:
		"""Block for the first frame, honouring the heartbeat deadline."""
		while True:
			message = self._read_or_report()
			if message is None:
				return None
			if not isinstance(message, Timeout):
				return message
			now = self._clock.monotonic()
			if now - self._last_heartbeat >= self._config.heartbeat_timeout:
				return None

	def _parse_request(self, message: dict[str, Any]) -> p.Request | None:
		try:
			return p.from_dict(p.Request, message)
		except p.ValidationError as exc:
			# No reliable id to correlate a malformed envelope; report best-effort.
			raw_id = message.get("id")
			self._send_error(raw_id if isinstance(raw_id, int) else 0, f"malformed request: {exc}")
			return None

	# -- dispatch -------------------------------------------------------------

	def _dispatch(self, req: p.Request) -> None:
		handler = self._handlers.get(req.cmd)
		if handler is None:
			self._send_error(req.id, f"unknown command {req.cmd!r}")
			return
		try:
			self._send_result(req.id, handler(req))
		except _WireError as exc:
			self._send_error(req.id, str(exc))
		except p.ValidationError as exc:
			self._send_error(req.id, f"invalid params for {req.cmd!r}: {exc}")

	def _build_handlers(self) -> dict[str, Callable[[p.Request], Any]]:
		introspection = "introspection commands arrive in session E"
		return {
			p.Command.HELLO: self._reject_second_hello,
			p.Command.PING: lambda _req: p.AckResult(),
			p.Command.PRESS_GESTURE: self._press_gesture,
			p.Command.GET_SPEECH: self._get_speech,
			p.Command.GET_LAST_SPEECH: self._get_last_speech,
			p.Command.GET_NEXT_SPEECH_INDEX: self._get_next_speech_index,
			p.Command.WAIT_FOR_SPEECH: self._wait_for_speech,
			p.Command.WAIT_FOR_SPEECH_TO_FINISH: self._wait_for_speech_to_finish,
			p.Command.GET_BRAILLE: self._get_braille,
			p.Command.GET_FOCUS_INFO: self._not_yet(introspection),
			p.Command.GET_STATE: self._not_yet(introspection),
			p.Command.GET_CONFIG: self._not_yet(introspection),
			p.Command.SET_CONFIG: self._not_yet(introspection),
		}

	def _reject_second_hello(self, _req: p.Request) -> Any:
		raise _WireError("already connected: hello may only be sent once")

	def _not_yet(self, why: str) -> Callable[[p.Request], Any]:
		def handler(_req: p.Request) -> Any:
			raise _WireError(f"not supported by this bridge build: {why}")

		return handler

	def _press_gesture(self, req: p.Request) -> Any:
		assert self._gestures is not None
		params = p.from_dict(p.PressGestureParams, req.params)
		for gesture_id in params.gestures:
			try:
				self._gestures.send(gesture_id)
			except ValueError as exc:
				raise _WireError(f"bad gesture {gesture_id!r}: {exc}") from exc
			self._transcript.gesture(gesture_id)
		return p.AckResult()

	def _get_speech(self, req: p.Request) -> Any:
		assert self._speech is not None
		params = p.from_dict(p.GetSpeechParams, req.params)
		text, from_index, to_index = self._speech.speech.get_since(params.sinceIndex)
		return p.SpeechResult(text=text, fromIndex=from_index, toIndex=to_index)

	def _get_last_speech(self, _req: p.Request) -> Any:
		assert self._speech is not None
		text, index = self._speech.speech.get_last()
		return p.LastSpeechResult(text=text, index=index)

	def _get_next_speech_index(self, _req: p.Request) -> Any:
		assert self._speech is not None
		return p.NextIndexResult(index=self._speech.speech.next_index())

	def _wait_for_speech(self, req: p.Request) -> Any:
		assert self._speech is not None
		params = p.from_dict(p.WaitForSpeechParams, req.params)
		found, index, text = self._speech.speech.wait_for(params.text, params.afterIndex, params.timeout)
		return p.WaitForSpeechResult(found=found, index=index, text=text)

	def _wait_for_speech_to_finish(self, req: p.Request) -> Any:
		assert self._speech is not None
		params = p.from_dict(p.WaitToFinishParams, req.params)
		return p.WaitToFinishResult(finished=self._speech.speech.wait_to_finish(params.timeout))

	def _get_braille(self, req: p.Request) -> Any:
		assert self._speech is not None
		params = p.from_dict(p.GetBrailleParams, req.params)
		text, from_index, to_index = self._speech.braille.get_since(params.sinceIndex)
		return p.BrailleResult(text=text, fromIndex=from_index, toIndex=to_index)

	# -- writing helpers ------------------------------------------------------

	def _send_result(self, request_id: int, result: Any) -> None:
		self._channel.write(p.Response(id=request_id, result=result))

	def _send_error(self, request_id: int, message: str) -> None:
		self._channel.write(p.Response(id=request_id, error=p.ErrorInfo(message=message)))
