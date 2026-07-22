# nvdaMcpBridge domain ports -- the Log port.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# ROLE: port (abc.ABC). The logging seam the domain and adapters both use.
#       Keeps every adapter that needs to log decoupled from NVDA's
#       ``logHandler`` so it stays unit-testable against a fake.
# IMPLEMENTED BY: adapters/nvda_log.py (wraps logHandler.log; NVDA edge);
#                 tests/fakes/log.py FakeLog (records messages in memory).
# USED BY: adapters/ini_bridge_config.py (warnings for unrecognised modes,
#          corrupt files); any future adapter that needs to log.

from __future__ import annotations

from abc import ABC, abstractmethod


class Log(ABC):
	"""Minimal logging facet: info, warning, error. Matches the subset of
	NVDA's ``logHandler.log`` that adapters actually use."""

	@abstractmethod
	def info(self, msg: str) -> None: ...

	@abstractmethod
	def warning(self, msg: str) -> None: ...

	@abstractmethod
	def error(self, msg: str, exc_info: bool = False) -> None: ...
