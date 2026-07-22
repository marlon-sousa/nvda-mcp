# nvdaMcpBridge adapters -- the Listener seam.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# ROLE: the accepting edge. An ADAPTER SEAM, not a domain port -- the domain
#       runs one session over a Transport and never learns how connections
#       arrive, so this interface lives with the adapters that use it.
# USED BY: adapters/bridge_server.py (its accept loop turns each connection into
#          a Session; it is the seam entry 9.1's control dialog drives too).
# IMPLEMENTED BY: adapters/tcp_listener.py (leaf, real socket; loopback only);
#                 tests/fakes/listener.py FakeListener (scripted connections).
#
# The contract mirrors Transport.recv on purpose: accept() blocks only up to a
# poll window and raises TimeoutError when idle, so the leaf is trivial and the
# server thread stays responsive to stop() without a dedicated wakeup pipe.

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
	from .transport import Transport


class ListenerClosed(Exception):
	"""Raised by :meth:`Listener.accept` once the listener has been closed.

	Its own signalling type, so it lives in this file with the port that raises
	it (same rule as ``ChannelClosed`` beside ``MessageChannel``).
	"""


class Listener(ABC):
	"""A bound, listening endpoint that yields one connection at a time."""

	@property
	@abstractmethod
	def endpoint(self) -> str:
		"""Human-readable accepting address (e.g. ``"127.0.0.1:8765"``).

		The value the status display in entry 9.1 shows; defined once ``open``
		has bound the socket.
		"""

	@abstractmethod
	def open(self) -> None:
		"""Bind and start listening. Raises on a bind failure (e.g. port in use)."""

	@abstractmethod
	def accept(self) -> Transport:
		"""Next connection, wrapped as a :class:`Transport`.

		Blocks up to a poll window and raises ``TimeoutError`` when no connection
		arrives (mirroring ``Transport.recv``), so the accept loop keeps checking
		whether it should stop. Raises :class:`ListenerClosed` once :meth:`close`
		has been called.
		"""

	@abstractmethod
	def close(self) -> None:
		"""Stop listening; idempotent, and unblocks a pending :meth:`accept`."""
