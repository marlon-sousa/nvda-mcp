# nvdaMcpBridge -- the NVDA global plugin (the NVDA edge).
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# This file imports NVDA and is therefore in pyright's ``ignore`` list (see
# pyproject.toml): it is the thin edge, kept deliberately small, with all real
# logic living in the strict-checked ``domain/``. It is validated by the
# milestone-6 live-NVDA integration tests, not by the type checker.
#
# SKELETON. Session B built the whole stdlib-only core (domain/ + adapters/ +
# wiring.py), all unit-tested headlessly. This plugin does NOT yet wire it to a
# live socket or to NVDA: the loopback server, the NVDA-backed AdapterFactory,
# the spy synth and the panic gesture are session C. Until then the plugin does
# nothing with side effects, so it is safe to leave installed.

from __future__ import annotations

import globalPluginHandler
from logHandler import log


class GlobalPlugin(globalPluginHandler.GlobalPlugin):
	"""Entry point NVDA instantiates when the addon loads.

	Inert placeholder: no socket bound, no hooks registered, no synth swapped.
	Session C wires this to ``wiring.serve`` per accepted connection.
	"""

	def __init__(self) -> None:
		super().__init__()
		log.debug("nvdaMcpBridge: loaded (inert skeleton; session server wired in session C)")

	def terminate(self) -> None:
		super().terminate()
