# nvda-mcp server package.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# Thin translator: MCP tool call -> bridge wire command -> result. The real
# FastMCP app and the v1 tools land in milestone 4 (session D). This module
# currently exposes only the console-script entry point so the package is
# installable and wired end to end.

from __future__ import annotations

__all__ = ["main", "__version__"]

__version__ = "0.1.0"


def main() -> None:
	"""Console-script entry point (``nvda-mcp``).

	Placeholder until the FastMCP server (milestone 4) is implemented.
	"""
	raise SystemExit(
		"nvda-mcp: the MCP server is not implemented yet (planned for milestone 4)."
	)
