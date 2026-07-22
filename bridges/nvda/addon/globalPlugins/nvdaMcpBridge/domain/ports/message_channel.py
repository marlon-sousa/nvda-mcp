# nvdaMcpBridge domain -- the MessageChannel port.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# ROLE: the session's request/response seam with the outside world.
# USED BY: the Session controller (its only I/O collaborator).
# IMPLEMENTED BY: adapters/json_lines_channel.py (JSON lines over a Transport);
#                 tests/fakes/message_channel.py FakeChannel (scripted messages).
#
# The domain deliberately knows nothing about bytes, sockets or JSON -- only
# that it can read a message, write one, and be closed. Everything below that
# (framing, encoding, the socket) lives behind this port in the adapters, which
# is why "pure Python" is not the test for whether code belongs in the domain.

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Final


class ChannelClosed(Exception):
	"""Raised by :meth:`MessageChannel.read_message` when the peer is gone.

	Part of the read contract, so it lives with the port rather than with any
	one implementation: the Session catches this to end the session.
	"""


class Timeout:
	"""Sentinel type meaning "no message yet" -- see :data:`TIMEOUT`.

	Also part of the read contract. Distinct from ``None`` (a valid JSON value)
	and from :class:`ChannelClosed` ("peer is gone"), so the Session can tell
	"quiet, go check your deadlines" apart from "finished". It is a class rather
	than a bare object so ``dict | Timeout`` narrows under a strict type checker.
	"""

	__slots__ = ()

	def __repr__(self) -> str:  # pragma: no cover - debug aid
		return "TIMEOUT"


#: The single :class:`Timeout` instance; test with ``isinstance(msg, Timeout)``.
TIMEOUT: Final = Timeout()


class MessageChannel(ABC):
	"""Reads/writes whole protocol messages, hiding all transport concerns."""

	@abstractmethod
	def read_message(self) -> dict[str, Any] | Timeout:
		"""Next message, or :data:`TIMEOUT` if none arrived within the poll window.

		The timeout is what lets the Session periodically regain control to check
		its heartbeat / inactivity deadlines while otherwise waiting on a client.
		Raises :class:`ChannelClosed` when the peer has gone away, and
		:class:`~...protocol.ValidationError` if a message is unreadable -- the
		Session reports that and carries on rather than dying on garbage bytes.
		"""

	@abstractmethod
	def write(self, message: Any) -> None:
		"""Send one message (a wire dataclass or plain dict)."""

	@abstractmethod
	def close(self) -> None: ...
