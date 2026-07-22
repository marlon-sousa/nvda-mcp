# nvdaMcpBridge tests -- shared test support that is NOT a port fake.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# Mirrors the `fakes` package (both are on sys.path via tests/conftest.py), but
# holds builders and helpers rather than port doubles -- e.g. assembling a
# SessionContext from fakes so a command handler can be tested with no Session.
# Import from the module that owns each helper (`from support.context import
# make_context`); no re-export facade here.
