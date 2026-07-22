# nvdaMcpBridge domain -- the pure, NVDA-free core of the bridge.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# Everything here is stdlib-only and importable under desktop Python: no NVDA,
# no sockets, no files, no JSON. Three roles, each in its own sub-package, so
# the path tells you what a file is:
#
#   ports/        the abstract seams the domain needs (abc.ABC, one per file).
#                 Implemented by adapters/, bound by wiring.py.
#   controllers/  the orchestrators. Handed the ports they need by wiring.py;
#                 they drive the entities and call out through the ports.
#                 This is where "who connects what" is answered.
#   entities/     the stateful things the bridge reasons about (the indexed
#                 speech/braille buffers). Pure; never perform IO.
#
# If a class is none of those three, it does not belong in the domain -- that is
# how the JSON-lines framing ended up (correctly) behind the MessageChannel port
# in adapters/json_lines_channel.py instead of here.
