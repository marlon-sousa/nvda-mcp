# nvdaMcpBridge adapters -- the Transport seam.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# ROLE: raw byte pipe. An ADAPTER SEAM, not a domain port -- the domain speaks
#       whole messages (see domain/ports/message_channel.py) and never sees
#       bytes, so this interface lives with the adapters that use it.
# USED BY: adapters/json_lines_channel.py (frames messages over it).
# IMPLEMENTED BY: adapters/socket_transport.py (leaf, real socket; session C);
#                 tests/fakes/transport.py FakeTransport (scripted bytes).

from __future__ import annotations

from abc import ABC, abstractmethod


class Transport(ABC):
	"""A byte pipe with a poll timeout."""

	@abstractmethod
	def recv(self) -> bytes:
		"""Next chunk; ``b""`` at EOF; raises ``TimeoutError`` when idle.

		A real socket with ``settimeout`` already behaves exactly this way, which
		is why the leaf implementation is almost nothing.
		"""

	@abstractmethod
	def sendall(self, data: bytes) -> None: ...

	@abstractmethod
	def close(self) -> None: ...
