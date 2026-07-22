# nvdaMcpBridge adapters -- the ConfigFile seam.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# ROLE: read and write a complete config file. An ADAPTER SEAM, not a domain
#       port -- the domain has no idea config is a file at all.
# USED BY: adapters/ini_bridge_config.py, which owns every decision (defaults,
#          validation, configparser vocabulary) and delegates raw IO here.
# IMPLEMENTED BY: adapters/text_config_file.py (leaf: real open/read/write);
#                 tests/fakes/config_file.py FakeConfigFile (in-memory string).

from __future__ import annotations

from abc import ABC, abstractmethod


class ConfigFile(ABC):
	"""Whole-file read/write; the leaf creates directories on first write."""

	@abstractmethod
	def read(self) -> str | None:
		"""Return the file contents, or None when the file does not exist."""

	@abstractmethod
	def write(self, content: str) -> None:
		"""Overwrite the file, creating parent directories as needed."""
