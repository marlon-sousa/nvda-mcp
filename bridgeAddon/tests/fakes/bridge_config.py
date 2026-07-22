# nvdaMcpBridge tests -- FakeBridgeConfig, standing in for the BridgeConfig port.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# FAKES: domain/ports/bridge_config.py

from __future__ import annotations

from nvdaMcpBridge.domain.entities.connection_mode import DEFAULT, ConnectionMode
from nvdaMcpBridge.domain.ports.bridge_config import BridgeConfig


class FakeBridgeConfig(BridgeConfig):
	"""An in-memory :class:`BridgeConfig` backed by a plain dict.

	Initialised with defaults so a test that does not care about config can
	construct it with no arguments; any test that needs a specific mode or
	auto-start preference passes them as keyword arguments.
	"""

	def __init__(self, *, mode: ConnectionMode = DEFAULT, auto_start: bool = False) -> None:
		self._mode = mode
		self._auto_start = auto_start

	def get_connection_mode(self) -> ConnectionMode:
		return self._mode

	def set_connection_mode(self, mode: ConnectionMode) -> None:
		self._mode = mode

	def get_auto_start(self) -> bool:
		return self._auto_start

	def set_auto_start(self, value: bool) -> None:
		self._auto_start = value
