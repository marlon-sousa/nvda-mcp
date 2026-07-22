# nvdaMcpBridge views -- driving actors that consume ports and adapter-layer objects.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# Views live outside the domain (they import wx, NVDA's GUI, and other NVDA-edge
# modules) but are NOT adapters -- they do not implement any domain port. They
# receive their dependencies through constructor injection, the same pattern as
# domain controllers, and are activated by the composition root (plugin.py).
#
# This package is in pyright's ``ignore`` list (see pyproject.toml) because its
# modules import wx and NVDA's GUI stack -- the full NVDA GUI surface, outside the
# domain boundary. It is validated by the live-NVDA checklist for each entry that
# adds a view.

# No re-exports -- import each view from its own file.
