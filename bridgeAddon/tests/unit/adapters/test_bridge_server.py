# Unit tests for adapters/bridge_server.py.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# BridgeServer is the connection edge's orchestrator, driven here against a fake
# listener and a fake session factory -- the same "upper adapter vs a fake seam"
# recipe JsonLinesChannel is tested with. The FakeSession blocks until the test
# ends it (finish() for a natural bye/EOF, or the server's own request_teardown
# on stop), so every state transition is observed deterministically rather than
# raced. The real socket + real Session live in the integration scenario.

from __future__ import annotations

import time
from typing import Callable

from fakes.listener import FakeListener
from fakes.transport import FakeTransport
from support.session import FakeSession

from nvdaMcpBridge.adapters.bridge_server import BridgeServer, ServerState, ServerStatus
from nvdaMcpBridge.adapters.ports.transport import Transport
from nvdaMcpBridge.domain.controllers.session import Session
from nvdaMcpBridge.domain.controllers.teardown_reason import TeardownReason


class RecordingFactory:
	"""A session factory that hands out FakeSessions and keeps them for the test."""

	def __init__(self) -> None:
		self.sessions: list[FakeSession] = []

	def __call__(self, transport: Transport) -> Session:
		session = FakeSession(transport)
		self.sessions.append(session)
		return session


def _wait_until(predicate: Callable[[], bool], timeout: float = 2.0) -> None:
	deadline = time.monotonic() + timeout
	while time.monotonic() < deadline:
		if predicate():
			return
		time.sleep(0.005)
	raise AssertionError("condition not met within timeout")


def _in_state(server: BridgeServer, state: ServerState) -> Callable[[], bool]:
	return lambda: server.status.state is state


# -- start / status ----------------------------------------------------------


def test_start_reports_listening_with_the_endpoint() -> None:
	listener = FakeListener(endpoint="127.0.0.1:8765")
	server = BridgeServer(listener, RecordingFactory())
	assert server.status == ServerStatus(ServerState.STOPPED, None)

	server.start()
	try:
		assert listener.opened is True
		assert server.status == ServerStatus(ServerState.LISTENING, "127.0.0.1:8765")
	finally:
		server.stop()
	assert server.status == ServerStatus(ServerState.STOPPED, None)


def test_start_twice_is_a_no_op() -> None:
	listener = FakeListener()
	server = BridgeServer(listener, RecordingFactory())
	server.start()
	try:
		server.start()  # already running: must not open again or spawn a rival thread
		assert server.status.state is ServerState.LISTENING
	finally:
		server.stop()


# -- accepting sessions ------------------------------------------------------


def test_accepted_connection_is_active_and_gets_the_transport() -> None:
	listener = FakeListener()
	factory = RecordingFactory()
	server = BridgeServer(listener, factory)
	server.start()
	try:
		transport = FakeTransport()
		listener.connect(transport)
		_wait_until(_in_state(server, ServerState.SESSION_ACTIVE))

		assert len(factory.sessions) == 1
		assert factory.sessions[0].transport is transport

		factory.sessions[0].finish()  # a natural bye/EOF end
		_wait_until(_in_state(server, ServerState.LISTENING))
	finally:
		server.stop()


def test_a_second_connection_starts_a_second_session() -> None:
	listener = FakeListener()
	factory = RecordingFactory()
	server = BridgeServer(listener, factory)
	server.start()
	try:
		first = FakeTransport()
		listener.connect(first)
		_wait_until(_in_state(server, ServerState.SESSION_ACTIVE))
		factory.sessions[0].finish()
		_wait_until(_in_state(server, ServerState.LISTENING))

		second = FakeTransport()
		listener.connect(second)
		_wait_until(_in_state(server, ServerState.SESSION_ACTIVE))
		factory.sessions[1].finish()
		_wait_until(_in_state(server, ServerState.LISTENING))

		assert [s.transport for s in factory.sessions] == [first, second]
	finally:
		server.stop()


# -- stopping ----------------------------------------------------------------


def test_stop_while_listening_joins_promptly() -> None:
	listener = FakeListener()
	server = BridgeServer(listener, RecordingFactory())
	server.start()

	started = time.monotonic()
	server.stop()
	assert time.monotonic() - started < 1.0
	assert server.status == ServerStatus(ServerState.STOPPED, None)
	assert listener.closes >= 1


def test_stop_during_an_active_session_tears_it_down() -> None:
	listener = FakeListener()
	factory = RecordingFactory()
	server = BridgeServer(listener, factory)
	server.start()

	listener.connect(FakeTransport())
	_wait_until(_in_state(server, ServerState.SESSION_ACTIVE))
	session = factory.sessions[0]
	session.started.wait(timeout=2.0)

	server.stop()

	assert session.teardown_reason is TeardownReason.EXTERNAL
	assert session.swapper.restores == 1  # the session's teardown promise ran
	assert server.status == ServerStatus(ServerState.STOPPED, None)


def test_stop_is_idempotent() -> None:
	listener = FakeListener()
	server = BridgeServer(listener, RecordingFactory())
	server.start()
	server.stop()
	server.stop()  # must not raise or hang
	assert server.status == ServerStatus(ServerState.STOPPED, None)


def test_stop_before_start_is_safe() -> None:
	server = BridgeServer(FakeListener(), RecordingFactory())
	server.stop()  # nothing to stop
	assert server.status == ServerStatus(ServerState.STOPPED, None)


# -- failure posture ---------------------------------------------------------


def test_a_listener_fault_stops_the_server() -> None:
	listener = FakeListener()
	server = BridgeServer(listener, RecordingFactory())
	server.start()
	try:
		listener.fail_next_accept(OSError("accept blew up"))
		_wait_until(_in_state(server, ServerState.STOPPED))
		assert server.status == ServerStatus(ServerState.STOPPED, None)
		assert listener.closes >= 1  # the socket was released on the way out
	finally:
		server.stop()
