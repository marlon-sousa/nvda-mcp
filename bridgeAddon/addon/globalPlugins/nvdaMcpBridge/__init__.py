# nvdaMcpBridge -- NVDA MCP Bridge global plugin.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# SKELETON. This establishes the addon package and loads inertly.
#
# Session B added the stdlib-only bridge core as sibling modules -- the session
# state machine (session.py), indexed speech/braille buffers (speech_buffer.py),
# JSON-lines framing (framing.py), the transcript log (transcript.py) and the
# adapter interfaces (adapters.py) -- all unit-tested headlessly. This plugin
# does NOT yet wire them to a live socket or to NVDA: the loopback server, the
# real NVDA adapters, the spy synth and the panic gesture are session C, which
# imports NVDA. Until then the plugin deliberately does nothing with side
# effects, so it is safe to install.

from __future__ import annotations

import globalPluginHandler
from logHandler import log


class GlobalPlugin(globalPluginHandler.GlobalPlugin):
	"""Entry point NVDA instantiates when the addon loads.

	Inert placeholder: no socket bound, no hooks registered, no synth swapped.
	"""

	def __init__(self) -> None:
		super().__init__()
		log.debug("nvdaMcpBridge: loaded (inert skeleton; no session server yet)")

	def terminate(self) -> None:
		super().terminate()
