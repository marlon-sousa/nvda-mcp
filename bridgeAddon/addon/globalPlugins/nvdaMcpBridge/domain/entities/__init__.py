# nvdaMcpBridge domain -- entities: the things the bridge reasons about.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# ROLE: stateful domain objects with behaviour of their own, one class per file.
# DRIVEN BY: the controllers (see domain/controllers/), never by adapters.
# DEPENDS ON: domain ports only (the Clock), never on NVDA, sockets or files.
#
# Entities hold the bridge's actual subject matter -- captured speech and
# braille, indexed so assertions are race-free. They are pure: an entity never
# performs IO, it is handed a port when it needs the outside world.
#
# No re-exports -- import each entity from its own file.
