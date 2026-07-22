# nvdaMcpBridge adapters -- RealClock: the production Clock.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# ROLE: LEAF adapter. IMPLEMENTS the Clock domain port with the stdlib clock.
# BUILT BY: wiring / plugin.py.
#
# Nothing here makes a decision, so nothing here is unit-tested; the code that
# reasons about time (deadlines, wait loops) lives in the domain and runs
# against FakeClock, whose sleep is an instant advance.

from __future__ import annotations

import time

from ..domain.ports.clock import Clock


class RealClock(Clock):
	"""The production :class:`~..domain.ports.Clock`: ``time.monotonic`` / ``time.sleep``."""

	def monotonic(self) -> float:
		return time.monotonic()

	def sleep(self, seconds: float) -> None:
		time.sleep(seconds)
