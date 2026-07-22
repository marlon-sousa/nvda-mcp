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
from nvdaMcpBridge.domain.entities.bridge_events import BridgeEvent, BridgeEventType
from fakes.event_bus import FakeEventBus


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
	assert session.torn_down == 1  # the session's teardown promise ran
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


class _BoomSession(Session):
	"""A session whose run() raises -- stands in for an unexpected session fault
	(e.g. a client that vanished in a way the transport did not map to EOF)."""

	def __init__(self, transport: Transport) -> None:
		self.transport = transport

	def run(self) -> None:
		raise RuntimeError("session blew up")

	def request_teardown(self, reason: TeardownReason) -> None:
		pass


def test_a_session_fault_does_not_take_the_server_down() -> None:
	listener = FakeListener()
	made: list[_BoomSession] = []

	def factory(transport: Transport) -> Session:
		session = _BoomSession(transport)
		made.append(session)
		return session

	server = BridgeServer(listener, factory)
	server.start()
	try:
		listener.connect(FakeTransport())
		_wait_until(lambda: len(made) == 1)
		# The faulting session must not stop the server: it returns to LISTENING
		# and accepts a second connection.
		_wait_until(_in_state(server, ServerState.LISTENING))
		listener.connect(FakeTransport())
		_wait_until(lambda: len(made) == 2)
		assert server.status.state is ServerState.LISTENING
	finally:
		server.stop()


# -- event bus ----------------------------------------------------------------


def _last_event(bus: FakeEventBus) -> BridgeEvent | None:
	return bus.events[-1] if bus.events else None


def test_emits_server_status_on_start() -> None:
	bus = FakeEventBus()
	listener = FakeListener(endpoint="127.0.0.1:8765")
	server = BridgeServer(listener, RecordingFactory(), event_bus=bus)
	server.start()
	try:
		evt = _last_event(bus)
		assert evt is not None
		assert evt.type is BridgeEventType.SERVER_STATUS
		assert evt.payload.state is ServerState.LISTENING
		assert evt.payload.endpoint == "127.0.0.1:8765"
	finally:
		server.stop()


def test_emits_server_status_on_stop() -> None:
	bus = FakeEventBus()
	server = BridgeServer(FakeListener(), RecordingFactory(), event_bus=bus)
	server.start()
	server.stop()
	evt = _last_event(bus)
	assert evt is not None
	assert evt.type is BridgeEventType.SERVER_STATUS
	assert evt.payload.state is ServerState.STOPPED


def test_emits_server_status_when_client_connects() -> None:
	bus = FakeEventBus()
	listener = FakeListener()
	server = BridgeServer(listener, RecordingFactory(), event_bus=bus)
	server.start()
	try:
		listener.connect(FakeTransport())
		_wait_until(lambda: any(
			e.payload.state is ServerState.SESSION_ACTIVE for e in bus.events
		))
	finally:
		server.stop()


def test_emits_server_status_when_client_disconnects() -> None:
	bus = FakeEventBus()
	listener = FakeListener()
	factory = RecordingFactory()
	server = BridgeServer(listener, factory, event_bus=bus)
	server.start()
	try:
		listener.connect(FakeTransport())
		_wait_until(_in_state(server, ServerState.SESSION_ACTIVE))
		factory.sessions[0].finish()
		_wait_until(_in_state(server, ServerState.LISTENING))
		assert any(
			e.payload.state is ServerState.LISTENING for e in bus.events
		)
	finally:
		server.stop()


def test_start_with_new_listener_switches_transport() -> None:
	bus = FakeEventBus()
	pipe_listener = FakeListener(endpoint="pipe")
	server = BridgeServer(pipe_listener, RecordingFactory(), event_bus=bus)
	server.start()
	try:
		assert server.status.endpoint == "pipe"
		assert pipe_listener.opened is True
		server.stop()

		# Start again with a different listener.
		tcp_listener = FakeListener(endpoint="127.0.0.1:8765")
		server.start(tcp_listener)
		assert server.status.endpoint == "127.0.0.1:8765"
		assert tcp_listener.opened is True
		assert pipe_listener.closes >= 1  # old listener was closed
	finally:
		server.stop()
