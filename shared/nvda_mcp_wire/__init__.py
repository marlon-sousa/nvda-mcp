# nvda-mcp shared wire package.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# The MCP server imports the wire contract from here. The NVDA addon does NOT
# import this package; its build copies ``protocol.py`` in as a local module,
# so the addon never carries a third-party dependency. Keep everything the two
# hosts share inside ``protocol.py`` (stdlib-only), and re-export it here for
# the server's convenience.

from nvda_mcp_wire.protocol import *  # noqa: F401,F403
