# nvdaMcpBridge domain -- the pure, NVDA-free core of the bridge.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# Everything in this package is stdlib-only and importable under desktop Python
# (no NVDA, no sockets). It depends on the abstract ports in ``ports.py``; the
# concrete implementations live in the sibling ``adapters/`` package and are
# bound to the ports by ``wiring.py``. Unit-tested headlessly with fakes.
