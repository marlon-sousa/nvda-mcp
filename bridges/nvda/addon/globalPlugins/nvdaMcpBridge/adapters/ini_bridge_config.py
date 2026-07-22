# nvdaMcpBridge adapters -- IniBridgeConfig: the BridgeConfig port backed by a
# profile-independent config.ini.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# ROLE: adapter (implements the BridgeConfig domain port). Holds every decision
#       (defaults, validation, configparser vocabulary) and delegates raw file IO
#       to a ConfigFile seam -- so it is fully unit-testable against a fake.
# IMPLEMENTS: domain/ports/bridge_config.py BridgeConfig.
# BUILT BY: plugin.py (the composition root), handing it a TextConfigFile.
# USED BY: plugin.py (reads mode on load, reads auto_start; exposes start_server),
#          views/bridge_dialog.py (via the port, injected by plugin.py).
#
# Does NOT import NVDA -- the config path comes from the TextConfigFile leaf
# built by plugin.py. Strict-checked by pyright.

from __future__ import annotations

import configparser
import io

from ..domain.entities.connection_mode import DEFAULT, ConnectionMode
from ..domain.ports.bridge_config import BridgeConfig
from ..domain.ports.log import Log
from .ports.config_file import ConfigFile

#: The section name in config.ini.
_SECTION = "nvdaMcpBridge"

#: Key names in config.ini for the two persisted values.
_KEY_MODE = "connectionMode"
_KEY_AUTO_START = "autoStart"


class IniBridgeConfig(BridgeConfig):
	"""Bridge preferences backed by a profile-independent config.ini.

	Reads return sensible defaults (``DEFAULT`` / ``False``) when no file
	exists yet or a key is missing; writes create the file on first save.
	Raw IO is delegated to the injected ConfigFile seam so the configparser
	decisions here are unit-testable.
	"""

	def __init__(self, file: ConfigFile, log: Log) -> None:
		self._file = file
		self._log = log

	# -- BridgeConfig implementation --------------------------------------------

	def get_connection_mode(self) -> ConnectionMode:
		parser = self._read()
		raw = parser.get(_SECTION, _KEY_MODE, fallback=DEFAULT.value)
		try:
			return ConnectionMode(raw)
		except ValueError:
			self._log.warning(
				f"nvdaMcpBridge: unrecognised connection mode {raw!r}; "
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
		return parser.getboolean(_SECTION, _KEY_AUTO_START, fallback=False)

	def set_auto_start(self, value: bool) -> None:
		parser = self._read()
		self._ensure_section(parser)
		parser.set(_SECTION, _KEY_AUTO_START, "true" if value else "false")
		self._write(parser)

	# -- internals --------------------------------------------------------------

	def _read(self) -> configparser.ConfigParser:
		parser = configparser.ConfigParser()
		raw = self._file.read()
		if raw is not None:
			try:
				parser.read_string(raw)
			except configparser.Error:
				self._log.warning(
					"nvdaMcpBridge: corrupt config.ini; using defaults"
				)
		return parser

	def _ensure_section(self, parser: configparser.ConfigParser) -> None:
		if not parser.has_section(_SECTION):
			parser.add_section(_SECTION)

	def _write(self, parser: configparser.ConfigParser) -> None:
		buf = io.StringIO()
		parser.write(buf)
		self._file.write(buf.getvalue())
