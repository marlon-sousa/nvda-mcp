#!/usr/bin/env python3
# Copy the canonical shared wire module into the addon package.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# The bridge imports the wire protocol as a LOCAL module (``from . import
# protocol``) so the addon never carries a third-party dependency. The single
# source of truth lives in ``../shared/nvda_mcp_wire/protocol.py``; this script
# copies it verbatim into the addon package. Run it (or scons, which invokes
# the same copy) before type-checking or building the addon. The copied file is
# gitignored -- it is a build artifact, never edited in place.

from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
SOURCE = _HERE.parent / "shared" / "nvda_mcp_wire" / "protocol.py"
DEST = _HERE / "addon" / "globalPlugins" / "nvdaMcpBridge" / "protocol.py"

_HEADER = (
	"# AUTO-GENERATED COPY -- do not edit.\n"
	"# Source of truth: shared/nvda_mcp_wire/protocol.py (run bridgeAddon/sync_shared.py).\n"
)


def sync() -> Path:
	if not SOURCE.is_file():
		raise SystemExit(f"shared wire module not found: {SOURCE}")
	DEST.parent.mkdir(parents=True, exist_ok=True)
	DEST.write_text(_HEADER + SOURCE.read_text(encoding="utf-8"), encoding="utf-8")
	return DEST


if __name__ == "__main__":
	dest = sync()
	sys.stdout.write(f"synced {SOURCE} -> {dest}\n")
