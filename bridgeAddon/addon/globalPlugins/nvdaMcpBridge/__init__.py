# nvdaMcpBridge -- NVDA MCP Bridge global plugin.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# SKELETON (milestone 1). This establishes the addon package and loads inertly.
# The loopback socket server, session state machine, speech/braille capture,
# gesture input and the fail-safe synth restoration are added in later
# milestones (sessions B and C). Until then the plugin deliberately does
# nothing with side effects, so it is safe to install.

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
