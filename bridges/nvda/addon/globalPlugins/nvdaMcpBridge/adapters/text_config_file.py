# nvdaMcpBridge adapters -- TextConfigFile: the ConfigFile leaf.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# ROLE: LEAF adapter. IMPLEMENTS the ConfigFile seam with real open/read/write.
#       No decisions -- no unit test file (the same rule as text_file_writer.py).
# USED BY: adapters/ini_bridge_config.py, via the seam, never directly.
# BUILT BY: plugin.py.

from __future__ import annotations

import os
from pathlib import Path

from .ports.config_file import ConfigFile


class TextConfigFile(ConfigFile):
	"""Real file backed by open/read/write. Parent directories created on write."""

	def __init__(self, path: str | os.PathLike[str]) -> None:
		self._path = Path(path)

	def read(self) -> str | None:
		try:
			return self._path.read_text(encoding="utf-8")
		except FileNotFoundError:
			return None

	def write(self, content: str) -> None:
		self._path.parent.mkdir(parents=True, exist_ok=True)
		self._path.write_text(content, encoding="utf-8")
