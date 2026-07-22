# nvdaMcpBridge tests -- FakeListener, standing in for the Listener seam.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# FAKES: adapters/ports/listener.py
#
# Lets a test drive BridgeServer's accept loop precisely, with no socket: queue
# a connection with connect(), let accept() report TimeoutError while idle
# (exactly as a real listener polls), arm a one-shot fault with fail_next_accept,
# and close() to make accept() raise ListenerClosed. It records open/close so a
# test can assert the server bound once and released the socket on stop.

from __future__ import annotations

import queue
import threading

from nvdaMcpBridge.adapters.ports.listener import Listener, ListenerClosed
from nvdaMcpBridge.adapters.ports.transport import Transport


class FakeListener(Listener):
	"""Yields scripted connections; times out when idle; ListenerClosed once closed."""

	def __init__(self, endpoint: str = "127.0.0.1:0", *, poll_timeout: float = 0.02) -> None:
		self._endpoint = endpoint
		self._poll_timeout = poll_timeout
		self._connections: queue.Queue[Transport] = queue.Queue()
		self._closed = threading.Event()
		self._fault: Exception | None = None
		self.opened = False
		self.closes = 0

	# -- test hooks ----------------------------------------------------------

	def connect(self, transport: Transport) -> None:
		"""Queue a connection the next accept() will return."""
		self._connections.put(transport)

	def fail_next_accept(self, error: Exception) -> None:
		"""Arm a one-shot fault: the next accept() raises ``error``."""
		self._fault = error

	# -- Listener ------------------------------------------------------------

	@property
	def endpoint(self) -> str:
		return self._endpoint

	def open(self) -> None:
		self.opened = True

	def accept(self) -> Transport:
		if self._closed.is_set():
			raise ListenerClosed
		if self._fault is not None:
			fault, self._fault = self._fault, None
			raise fault
		try:
			return self._connections.get(timeout=self._poll_timeout)
		except queue.Empty:
			if self._closed.is_set():
				raise ListenerClosed from None
			raise TimeoutError from None

	def close(self) -> None:
		self.closes += 1
		self._closed.set()
