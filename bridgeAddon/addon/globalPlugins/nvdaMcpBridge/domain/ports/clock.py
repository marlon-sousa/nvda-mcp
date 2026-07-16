# nvdaMcpBridge domain -- the Clock port.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.

from __future__ import annotations

from abc import ABC, abstractmethod


class Clock(ABC):
	"""Monotonic time + sleep, injected wherever time is read or waited on.

	Fakes advance only when told, so timeout/heartbeat/inactivity behaviour is
	exercised without ever sleeping in real time.
	"""

	@abstractmethod
	def monotonic(self) -> float:
		"""Seconds from an arbitrary fixed origin; only differences matter."""

	@abstractmethod
	def sleep(self, seconds: float) -> None:
		"""Block for ``seconds`` (a fake may make this an instant clock advance)."""
