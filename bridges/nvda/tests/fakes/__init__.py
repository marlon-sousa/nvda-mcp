# nvdaMcpBridge tests -- the fakes.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# One fake per file, MIRRORING the port it stands in for:
#   tests/fakes/clock.py  <->  domain/ports/clock.py
# so "what fakes this port?" is answered by the path, exactly as tests/unit/
# mirrors the source. Same house rules as the addon: one class per file, no
# re-export facades -- import each from its own file
# (``from fakes.clock import FakeClock``).
#
# Each fake subclasses the ABC it stands in for, so a fake that drifts from its
# port fails at construction. They are hand-written and STATEFUL rather than
# mocks; see AGENTS.md ("Testing") for the reasoning.
