# nvdaMcpBridge domain -- the ports (abstract interfaces the domain depends on).
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# These are the seams of the hexagon, ONE PORT PER FILE. The domain (session
# state machine, speech buffers, framing) is written against these ABCs and
# nothing else; the ``adapters/`` package provides one concrete subclass of each
# (NVDA-backed in production, in-memory fakes in tests), and ``wiring.py`` is the
# only place that binds the two together.
#
# They are ``abc.ABC`` with ``@abstractmethod`` -- not ``typing.Protocol`` -- on
# purpose: an adapter that forgets a method fails loudly at construction, and
# the interface itself can never be instantiated. A port's own DTO (e.g.
# ``AdapterSet``) lives in the same file as the port that returns it.
#
# This module is deliberately EMPTY of re-exports: callers import each port from
# its own file (``from ..ports.clock import Clock``), so every import names the
# file it comes from and a module's dependencies are exactly the ports it lists
# -- rather than a facade that re-aggregates the seams we split apart.
