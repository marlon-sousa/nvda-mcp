# nvda-mcp shared wire package.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# Everything the two hosts share lives in ``protocol.py`` (stdlib-only);
# import from there: ``from nvda_mcp_wire.protocol import Request``. This file
# carries documentation only, never re-exports (AGENTS.md) — so both halves
# address the contract the same way: the server via this package's
# ``protocol`` module, the addon via its build-time copy of the same file.
