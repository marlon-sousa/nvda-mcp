# nvdaMcpBridge test doubles -- FakeConfigFile: the ConfigFile port in memory.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# ROLE: fake (subclasses ConfigFile). An in-memory string backend so
#       IniBridgeConfig is unit-tested without touching a filesystem.

from __future__ import annotations

from nvdaMcpBridge.adapters.ports.config_file import ConfigFile


class FakeConfigFile(ConfigFile):
	"""ConfigFile backed by a plain string; None means "file does not exist"."""

	def __init__(self, content: str | None = None) -> None:
		self._content = content

	def read(self) -> str | None:
		return self._content

	def write(self, content: str) -> None:
		self._content = content
