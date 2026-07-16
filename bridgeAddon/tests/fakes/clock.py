# nvdaMcpBridge tests -- FakeClock, standing in for the Clock port.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# FAKES: domain/ports/clock.py

from __future__ import annotations

from nvdaMcpBridge.domain.ports.clock import Clock


class FakeClock(Clock):
	"""A :class:`Clock` whose time only moves on demand.

	``sleep`` is an instant advance, which is what lets the domain's wait loops
	run to their deadline in microseconds. (It is also why freezegun /
	time-machine would not help here: they patch the global clock but leave
	``time.sleep`` real, so a 5-second timeout would take 5 real seconds.)
	"""

	def __init__(self, start: float = 0.0) -> None:
		self._now = start
		self.sleeps: list[float] = []

	def monotonic(self) -> float:
		return self._now

	def sleep(self, seconds: float) -> None:
		self.sleeps.append(seconds)
		self._now += seconds

	def advance(self, seconds: float) -> None:
		self._now += seconds
