# Integration scenario: a whole session over a REAL socket, headless.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# The 9a connection stack proven end to end: a real TcpListener on an ephemeral
# loopback port + BridgeServer + a FakeAdapterFactory, with a client socket
# dialling in and speaking raw protocol over its own SocketTransport +
# JsonLinesChannel. Everything below the NVDA edge is real -- the accept loop,
# the framing, the dispatch, the teardown -- so this runs in CI exactly like the
# loopback roundtrip, just over TCP instead of a queue. It is what proves the
# server the plugin will build in 9c actually works, and that sessions run
# sequentially against one server.

from __future__ import annotations

import socket
import struct
import time
from pathlib import Path
from typing import Any

from fakes.adapter_factory import FakeAdapterFactory
from fakes.announcer import FakeAnnouncer
from fakes.log_capture import FakeLogCapture
from fakes.session_signals import FakeSessionSignals

from nvdaMcpBridge import protocol as p
from nvdaMcpBridge.adapters.bridge_server import BridgeServer, ServerState
from nvdaMcpBridge.adapters.json_lines_channel import JsonLinesChannel
from nvdaMcpBridge.adapters.socket_transport import SocketTransport
from nvdaMcpBridge.adapters.tcp_listener import TcpListener
from nvdaMcpBridge.domain.controllers.commands.registry import NVDA_CAPABILITIES
from nvdaMcpBridge.domain.controllers.session import Session
from nvdaMcpBridge.domain.ports.message_channel import Timeout
from nvdaMcpBridge.wiring import build_session


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


def _dial(endpoint: str | None) -> JsonLinesChannel:
	assert endpoint is not None
	host, port = endpoint.rsplit(":", 1)
	client = socket.create_connection((host, int(port)), timeout=5.0)
	return JsonLinesChannel(SocketTransport(client))


def _wait_until(predicate: Any, timeout: float = 2.0) -> None:
	deadline = time.monotonic() + timeout
	while time.monotonic() < deadline:
		if predicate():
			return
		time.sleep(0.005)
	raise AssertionError("condition not met within timeout")


def test_a_whole_session_over_a_real_socket(tmp_path: Path) -> None:
	factories: list[FakeAdapterFactory] = []

	def session_factory(transport: Any) -> Session:
		# A fresh fake NVDA per session; kept so the test can assert capture was
		# stopped (the filter unregistered) on each teardown.
		factory = FakeAdapterFactory(speech={"NVDA+f7": ["Elements list dialog"]})
		factories.append(factory)
		return build_session(
			transport, factory, tmp_path, "2026.1.0", FakeSessionSignals(), FakeAnnouncer(), FakeLogCapture()
		)

	listener = TcpListener("127.0.0.1", 0)
	server = BridgeServer(listener, session_factory)
	server.start()
	try:
		assert server.status.state is ServerState.LISTENING
		endpoint = server.status.endpoint

		# -- first session ---------------------------------------------------
		agent = _dial(endpoint)
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
		agent = _dial(endpoint)
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

	server = BridgeServer(TcpListener("127.0.0.1", 0), session_factory)
	server.start()
	started = time.monotonic()
	server.stop()
	assert time.monotonic() - started < 2.0
	assert server.status.state is ServerState.STOPPED


def test_an_abruptly_reset_client_does_not_kill_the_server(tmp_path: Path) -> None:
	# Regression: a client that crashes mid-session resets the connection (RST /
	# WinError 10054). The server must treat that as EOF, end the session, and
	# keep serving -- not let the exception take the accept loop down.
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

	server = BridgeServer(TcpListener("127.0.0.1", 0), session_factory)
	server.start()
	try:
		endpoint = server.status.endpoint
		assert endpoint is not None
		host, port = endpoint.rsplit(":", 1)

		# Open a session, then abort the connection with a RST (SO_LINGER 0).
		raw = socket.create_connection((host, int(port)), timeout=5.0)
		agent = JsonLinesChannel(SocketTransport(raw))
		agent.write(_request(1, "hello", mode="silent", protocolVersion=p.PROTOCOL_VERSION))
		_read_reply(agent)
		raw.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
		raw.close()  # -> RST to the bridge

		# The server survives: back to LISTENING, and a fresh session still works.
		_wait_until(lambda: server.status.state is ServerState.LISTENING, timeout=5.0)
		agent2 = _dial(endpoint)
		try:
			agent2.write(_request(1, "hello", mode="silent", protocolVersion=p.PROTOCOL_VERSION))
			assert _read_reply(agent2)["result"]["mode"] == "silent"
			agent2.write(_request(2, "bye"))
			assert _read_reply(agent2)["result"] == {"ok": True}
		finally:
			agent2.close()
	finally:
		server.stop()
