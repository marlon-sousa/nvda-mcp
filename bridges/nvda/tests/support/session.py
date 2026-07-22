# nvdaMcpBridge tests -- FakeSession, a controllable stand-in for the Session.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# NOT a port double (Session is a controller, not a port), so it lives in
# support/ rather than fakes/. It exists to test BridgeServer's connection
# lifecycle in isolation: driving a real Session would drag in the whole
# handshake/dispatch stack the socket integration scenario already exercises.
#
# It subclasses Session so BridgeServer sees a real Session type, but overrides
# only the two methods BridgeServer calls -- run() and request_teardown() -- and
# skips Session.__init__ (nothing here reads the lifecycle fields). run() blocks
# until either request_teardown (stop path) or finish() (a natural bye/EOF end),
# then counts a teardown in a finally -- standing in for the real Session's
# teardown work (stopping the sources so speech flows again). started lets a test
# wait for the session to actually be running before it acts.

from __future__ import annotations

import threading

from nvdaMcpBridge.domain.controllers.session import Session
from nvdaMcpBridge.domain.controllers.teardown_reason import TeardownReason


class FakeSession(Session):
	"""A Session whose run() blocks until told to end; records its teardown."""

	def __init__(self, transport: object) -> None:
		# Deliberately no super().__init__: BridgeServer only calls run() and
		# request_teardown(), both overridden below.
		self.transport = transport
		self.teardown_reason: TeardownReason | None = None
		self.torn_down = 0
		self.started = threading.Event()
		self._done = threading.Event()

	def run(self) -> None:
		self.started.set()
		try:
			self._done.wait()
		finally:
			# The real Session's teardown always runs (stopping capture so speech
			# resumes); the fake counts it so "stop tore the session down" is
			# observable.
			self.torn_down += 1

	def request_teardown(self, reason: TeardownReason) -> None:
		self.teardown_reason = reason
		self._done.set()

	def finish(self) -> None:
		"""Simulate a natural end (bye / EOF): run() returns with no teardown reason."""
		self._done.set()
