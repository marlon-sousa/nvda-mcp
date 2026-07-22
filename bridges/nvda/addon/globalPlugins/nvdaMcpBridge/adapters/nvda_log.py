# nvdaMcpBridge adapters -- NvdaLog: the Log port backed by NVDA's logHandler.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# ROLE: adapter (implements the Log domain port). Wraps NVDA's ``logHandler.log``
#       (which is a stdlib Logger instance). On pyright's ignore list.
# IMPLEMENTS: domain/ports/log.py Log.
# BUILT BY: plugin.py (the composition root), handed to every adapter that logs.
# USED BY: adapters/ini_bridge_config.py (via the port, injected).

from __future__ import annotations

from logHandler import log

from ..domain.ports.log import Log


class NvdaLog(Log):
	"""Thin wrapper around NVDA's root logger."""

	def info(self, msg: str) -> None:
		log.info(msg)

	def warning(self, msg: str) -> None:
		log.warning(msg)

	def error(self, msg: str, exc_info: bool = False) -> None:
		log.error(msg, exc_info=exc_info)
