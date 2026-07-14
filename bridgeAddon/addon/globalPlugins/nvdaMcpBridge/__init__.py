# nvdaMcpBridge -- NVDA MCP Bridge addon package.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# NVDA loads a global plugin as ``globalPlugins.<name>.GlobalPlugin``. We expose
# that class **lazily** via a module-level ``__getattr__`` (PEP 562) so that
# importing this package does NOT import ``plugin.py`` -- and therefore does not
# import NVDA. The headless tests import ``nvdaMcpBridge.domain.*`` directly and
# never touch NVDA; only NVDA's own ``.GlobalPlugin`` access pulls in the edge.

from __future__ import annotations

from typing import Any


def __getattr__(name: str) -> Any:
	if name == "GlobalPlugin":
		from .plugin import GlobalPlugin

		return GlobalPlugin
	raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
