# nvdaMcpBridge adapters -- IniBridgeConfig: the BridgeConfig port backed by a
# profile-independent config.ini.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# ROLE: adapter (implements the BridgeConfig domain port). Uses stdlib configparser
#       to read/write <configPath>\nvdaMcpBridge\config\config.ini -- independent
#       of NVDA's profile-switching config.conf so the bridge's connection mode and
#       auto-start preference survive profile switches unchanged.
# IMPLEMENTS: domain/ports/bridge_config.py BridgeConfig.
# BUILT BY: plugin.py (the composition root), passing the config dir under the
#           bridge's logs directory.
# USED BY: plugin.py (reads mode on load, reads auto_start), views/bridge_dialog.py
#          (via the port, injected by plugin.py).
#
# Imports globalVars from NVDA and is therefore in pyright's ``ignore`` list (see
# pyproject.toml). It makes no decisions beyond what configparser already guarantees
# -- deliberately not unit-tested; covered by the live-NVDA checklist.

from __future__ import annotations

import configparser
import os
from typing import TYPE_CHECKING

import globalVars
from logHandler import log

from ..domain.entities.connection_mode import DEFAULT, ConnectionMode
from ..domain.ports.bridge_config import BridgeConfig

if TYPE_CHECKING:
	from typing import Final

#: The section name in config.ini.
_SECTION: "Final" = "nvdaMcpBridge"

#: Key names in config.ini for the two persisted values.
_KEY_MODE: "Final" = "connectionMode"
_KEY_AUTO_START: "Final" = "autoStart"


class IniBridgeConfig(BridgeConfig):
	"""Bridge preferences backed by a profile-independent config.ini.

	The file lives at ``<configPath>\\nvdaMcpBridge\\config\\config.ini`` -- sibling
	to the logs directory the bridge already owns (transcripts, NVDA log captures).
	Reads return sensible defaults (``DEFAULT`` / ``True``) when no file exists yet;
	writes create the directory and file on first save.
	"""

	def __init__(self, config_dir: str) -> None:
		self._path = os.path.join(config_dir, "config.ini")

	# -- BridgeConfig implementation --------------------------------------------

	def get_connection_mode(self) -> ConnectionMode:
		parser = self._read()
		raw = parser.get(_SECTION, _KEY_MODE, fallback=DEFAULT.value)
		try:
			return ConnectionMode(raw)
		except ValueError:
			log.warning(
				f"nvdaMcpBridge: unrecognised connection mode {raw!r} in {self._path}; "
				f"using default ({DEFAULT.value})"
			)
			return DEFAULT

	def set_connection_mode(self, mode: ConnectionMode) -> None:
		parser = self._read()
		self._ensure_section(parser)
		parser.set(_SECTION, _KEY_MODE, mode.value)
		self._write(parser)

	def get_auto_start(self) -> bool:
		parser = self._read()
		return parser.getboolean(_SECTION, _KEY_AUTO_START, fallback=True)

	def set_auto_start(self, value: bool) -> None:
		parser = self._read()
		self._ensure_section(parser)
		parser.set(_SECTION, _KEY_AUTO_START, "true" if value else "false")
		self._write(parser)

	# -- internals --------------------------------------------------------------

	def _read(self) -> configparser.ConfigParser:
		parser = configparser.ConfigParser()
		if os.path.isfile(self._path):
			parser.read(self._path, encoding="utf-8")
		return parser

	def _ensure_section(self, parser: configparser.ConfigParser) -> None:
		if not parser.has_section(_SECTION):
			parser.add_section(_SECTION)

	def _write(self, parser: configparser.ConfigParser) -> None:
		os.makedirs(os.path.dirname(self._path), exist_ok=True)
		with open(self._path, "w", encoding="utf-8") as f:
			parser.write(f)
