# nvdaMcpBridge domain -- controllers: the orchestrators.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# ROLE: the use-case orchestrators, one per file. A controller is handed the
# ports it needs by wiring.py, then runs a whole use case -- driving the
# entities and calling out through ports. It is "the answer to who connects
# what" at runtime: the Session reads a hello, asks the AdapterFactory to build
# the mode's collaborators, wires the buffers to them, dispatches commands, and
# on every teardown path restores the user's synth.
#
# DEPENDS ON: domain ports and entities only -- never on NVDA, sockets, or files.
# A controller's collaborators are all ports, so it is unit-tested headlessly
# with fakes.
#
# No re-exports -- import each controller from its own file.
