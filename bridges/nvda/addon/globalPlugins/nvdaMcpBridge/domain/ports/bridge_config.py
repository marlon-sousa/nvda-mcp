# nvdaMcpBridge domain -- the BridgeConfig port.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# ROLE: domain port. The contract the dialog (and plugin.py) read/write persisted
#       preferences through -- without knowing they're an .ini file.
# IMPLEMENTED BY: adapters/ini_bridge_config.py (production, configparser-backed,
#                 profile-independent .ini file under <configPath>\nvdaMcpBridge\config\),
#                 tests/fakes/bridge_config.py (in-memory dict for tests).
# USED BY: plugin.py (reads mode on load, reads auto_start; exposes rebuild_server),
#          views/bridge_dialog.py (reads/writes both values, injected via constructor).

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
	from ..entities.connection_mode import ConnectionMode


class BridgeConfig(ABC):
	"""Persisted bridge preferences: connection mode and auto-start.

	Profile-independent on purpose -- NVDA's config.conf is profile-aware, and
	switching profiles resets it to the active profile's values. The bridge's
	connection mode and auto-start preference are machine-wide settings; they
	should survive a profile switch unchanged.
	"""

	@abstractmethod
	def get_connection_mode(self) -> ConnectionMode:
		"""The persisted connection mode, or DEFAULT when no file exists yet."""

	@abstractmethod
	def set_connection_mode(self, mode: ConnectionMode) -> None:
		"""Persist *mode*; creates the directory and file on first save."""

	@abstractmethod
	def get_auto_start(self) -> bool:
		"""Whether to auto-start the bridge on NVDA load. Default ``False``."""

	@abstractmethod
	def set_auto_start(self, value: bool) -> None:
		"""Persist *value*; creates the directory and file on first save."""
