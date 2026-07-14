# nvdaMcpBridge adapters -- the production Clock.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.

from __future__ import annotations

import time

from ..domain.ports import Clock


class RealClock(Clock):
	"""The production :class:`~..domain.ports.Clock`: ``time.monotonic`` / ``time.sleep``."""

	def monotonic(self) -> float:
		return time.monotonic()

	def sleep(self, seconds: float) -> None:
		time.sleep(seconds)
