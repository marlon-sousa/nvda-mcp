# Integration scenario: a whole session over a REAL named pipe, headless.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# Spec 0010's proof: the same 9a connection stack (BridgeServer + a
# FakeAdapterFactory) proven over TCP in test_socket_session_roundtrip.py,
# this time behind a real NamedPipeListener on a unique per-test pipe name (the
# pipe analogue of TCP's ephemeral port 0) -- everything below the NVDA edge is
# real, so this is what proves NamedPipeListener/NamedPipeTransport are truly
# interchangeable with TcpListener/SocketTransport behind the Listener/
# Transport seams, not just similar. Runs on CI (windows-latest); no NVDA
# needed -- a named pipe is plain OS-level IPC.
#
# Deliberately a near-line-for-line mirror of test_socket_session_roundtrip.py:
# where the two differ is exactly where the leaf differs (listener + dial), and
# nowhere else -- that symmetry *is* the proof.

from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import Any

from fakes.adapter_factory import FakeAdapterFactory
from fakes.announcer import FakeAnnouncer
from fakes.log_capture import FakeLogCapture
from fakes.session_signals import FakeSessionSignals

from nvdaMcpBridge import protocol as p
from nvdaMcpBridge.adapters import named_pipe_transport
from nvdaMcpBridge.adapters.bridge_server import BridgeServer, ServerState
from nvdaMcpBridge.adapters.json_lines_channel import JsonLinesChannel
from nvdaMcpBridge.adapters.named_pipe_listener import NamedPipeListener
from nvdaMcpBridge.domain.controllers.commands.registry import NVDA_CAPABILITIES
from nvdaMcpBridge.domain.controllers.session import Session
from nvdaMcpBridge.domain.ports.message_channel import Timeout
from nvdaMcpBridge.wiring import build_session


def _unique_pipe_name() -> str:
	# The pipe analogue of TCP's port 0: a fresh name per test so parallel runs
	# (and a stray live bridge on the real DEFAULT_PIPE_NAME, if one happens to
	# be running on this machine) never collide.
	return rf"\\.\pipe\nvdaMcpBridge-test-{uuid.uuid4()}"


def _request(id: int, cmd: str, **params: Any) -> p.Request:
	return p.Request(id=id, cmd=cmd, params=dict(params))


def _read_reply(agent: JsonLinesChannel, timeout: float = 5.0) -> dict[str, Any]:
	"""Read past the poll-timeouts until the bridge actually answers."""
	deadline = time.monotonic() + timeout
	while time.monotonic() < deadline:
		message = agent.read_message()
		if not isinstance(message, Timeout):
			return message
	raise AssertionError("no reply from the bridge within timeout")


def _dial(pipe_name: str) -> JsonLinesChannel:
	return JsonLinesChannel(named_pipe_transport.dial(pipe_name))


def _wait_until(predicate: Any, timeout: float = 2.0) -> None:
	deadline = time.monotonic() + timeout
	while time.monotonic() < deadline:
		if predicate():
			return
		time.sleep(0.005)
	raise AssertionError("condition not met within timeout")


def test_a_whole_session_over_a_real_named_pipe(tmp_path: Path) -> None:
	factories: list[FakeAdapterFactory] = []

	def session_factory(transport: Any) -> Session:
		# A fresh fake NVDA per session; kept so the test can assert capture was
		# stopped (the filter unregistered) on each teardown.
		factory = FakeAdapterFactory(speech={"NVDA+f7": ["Elements list dialog"]})
		factories.append(factory)
		return build_session(
			transport, factory, tmp_path, "2026.1.0", FakeSessionSignals(), FakeAnnouncer(), FakeLogCapture()
		)

	pipe_name = _unique_pipe_name()
	listener = NamedPipeListener(pipe_name)
	server = BridgeServer(listener, session_factory)
	server.start()
	try:
		assert server.status.state is ServerState.LISTENING
		assert server.status.endpoint == pipe_name

		# -- first session ---------------------------------------------------
		agent = _dial(pipe_name)
		try:
			agent.write(_request(1, "hello", mode="silent", protocolVersion=p.PROTOCOL_VERSION))
			hello = _read_reply(agent)
			assert hello["result"]["mode"] == "silent"
			assert hello["result"]["reader"] == {"name": "nvda", "version": "2026.1.0"}
			assert hello["result"]["capabilities"] == [c.value for c in NVDA_CAPABILITIES]

			payload = {"u": "olá café \U0001f600", "nested": [1, 2, {"x": True}]}
			agent.write(_request(2, "echo", payload=payload))
			assert _read_reply(agent)["result"]["payload"] == payload

			agent.write(_request(3, "pressGesture", gestures=["NVDA+f7"]))
			assert _read_reply(agent)["result"] == {"ok": True}
			agent.write(_request(4, "waitForSpeechToFinish", timeout=3.0))
			assert _read_reply(agent, timeout=6.0)["result"]["finished"] is True
			agent.write(_request(5, "getSpeech", sinceIndex=0))
			assert "Elements list dialog" in _read_reply(agent)["result"]["text"]

			agent.write(_request(6, "bye"))
			assert _read_reply(agent)["result"] == {"ok": True}
		finally:
			agent.close()

		# The session ended (bye) and the server is accepting again, no restart.
		_wait_until(lambda: server.status.state is ServerState.LISTENING)
		assert factories[0].speech_source.stopped == 1

		# -- second session, same server -------------------------------------
		agent = _dial(pipe_name)
		try:
			agent.write(_request(1, "hello", mode="silent", protocolVersion=p.PROTOCOL_VERSION))
			assert _read_reply(agent)["result"]["mode"] == "silent"
			agent.write(_request(2, "bye"))
			assert _read_reply(agent)["result"] == {"ok": True}
		finally:
			agent.close()

		_wait_until(lambda: server.status.state is ServerState.LISTENING)
		assert len(factories) == 2
		assert factories[1].speech_source.stopped == 1
	finally:
		server.stop()

	assert server.status.state is ServerState.STOPPED


def test_stop_ends_an_idle_server_promptly(tmp_path: Path) -> None:
	# A server that never sees a connection still stops cleanly and promptly --
	# the accept poll window, not a client, is what bounds stop().
	def session_factory(transport: Any) -> Session:
		return build_session(
			transport,
			FakeAdapterFactory(),
			tmp_path,
			"2026.1.0",
			FakeSessionSignals(),
			FakeAnnouncer(),
			FakeLogCapture(),
		)

	server = BridgeServer(NamedPipeListener(_unique_pipe_name()), session_factory)
	server.start()
	started = time.monotonic()
	server.stop()
	assert time.monotonic() - started < 2.0
	assert server.status.state is ServerState.STOPPED


def test_an_abruptly_closed_client_does_not_kill_the_server(tmp_path: Path) -> None:
	# Regression, the pipe analogue of the TCP scenario's RST test: a client
	# that vanishes mid-session without `bye` must not take the accept loop
	# down -- the next read reports EOF (ERROR_BROKEN_PIPE), same as a reset
	# socket reporting b"".
	def session_factory(transport: Any) -> Session:
		return build_session(
			transport,
			FakeAdapterFactory(),
			tmp_path,
			"2026.1.0",
			FakeSessionSignals(),
			FakeAnnouncer(),
			FakeLogCapture(),
		)

	pipe_name = _unique_pipe_name()
	server = BridgeServer(NamedPipeListener(pipe_name), session_factory)
	server.start()
	try:
		agent = _dial(pipe_name)
		agent.write(_request(1, "hello", mode="silent", protocolVersion=p.PROTOCOL_VERSION))
		_read_reply(agent)
		agent.close()  # no `bye` -- just vanish

		# The server survives: back to LISTENING, and a fresh session still works.
		_wait_until(lambda: server.status.state is ServerState.LISTENING, timeout=5.0)
		agent2 = _dial(pipe_name)
		try:
			agent2.write(_request(1, "hello", mode="silent", protocolVersion=p.PROTOCOL_VERSION))
			assert _read_reply(agent2)["result"]["mode"] == "silent"
			agent2.write(_request(2, "bye"))
			assert _read_reply(agent2)["result"] == {"ok": True}
		finally:
			agent2.close()
	finally:
		server.stop()


def test_accept_and_recv_report_timeout_when_idle() -> None:
	# The poll-timeout contract every Listener/Transport leaf must honour
	# (Listener.accept, Transport.recv): sockets get it for free from
	# settimeout: the named-pipe leaf earns it from overlapped I/O, so it is
	# worth asserting directly rather than only inferring it from the scenarios
	# above completing in reasonable time.
	pipe_name = _unique_pipe_name()
	listener = NamedPipeListener(pipe_name, accept_timeout=0.2)
	listener.open()
	try:
		start = time.monotonic()
		try:
			listener.accept()
			raise AssertionError("expected TimeoutError")
		except TimeoutError:
			pass
		assert 0.15 < time.monotonic() - start < 1.0

		client = named_pipe_transport.dial(pipe_name)
		try:
			server_side = listener.accept()
			try:
				start = time.monotonic()
				try:
					server_side.recv()
					raise AssertionError("expected TimeoutError")
				except TimeoutError:
					pass
				assert 0.0 < time.monotonic() - start < 1.0

				client.sendall(b"hi")
				assert server_side.recv() == b"hi"
			finally:
				server_side.close()
		finally:
			client.close()
	finally:
		listener.close()
