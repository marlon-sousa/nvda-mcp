# nvdaMcpBridge domain -- controllers: the orchestrators.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# ROLE: a controller is handed the PORTS it needs by wiring.py, and orchestrates
#       a whole use case with them -- driving the entities (domain/entities/) and
#       calling out through the ports. It is the answer to "who connects what".
# CONSTRUCTED BY: wiring.py (the composition root), never by an adapter.
# DEPENDS ON: domain ports + domain entities. Never NVDA, sockets, files or JSON.
#
# Today there is exactly one: Session, which runs one bridge session end to end.
#
# No re-exports -- import each controller from its own file.
