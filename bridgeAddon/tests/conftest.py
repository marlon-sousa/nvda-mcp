# Headless test harness for the bridge core (session B).
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# The bridge domain imports NVDA nowhere, and the package ``__init__`` exposes
# GlobalPlugin lazily (so importing the package does not import NVDA either).
# The harness therefore only needs to: (1) sync the shared wire module in so
# ``from .. import protocol`` resolves to the exact shipped bytes; (2) put the
# ``globalPlugins`` directory on ``sys.path`` so ``import nvdaMcpBridge.*`` works.
# No NVDA stubs required.
#
# It also holds the fixtures shared across test modules. See AGENTS.md
# ("Testing") for when a fixture is the right tool and when it is not.

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_TESTS_DIR = Path(__file__).resolve().parent
_ADDON_ROOT = _TESTS_DIR.parent
_GLOBAL_PLUGINS = _ADDON_ROOT / "addon" / "globalPlugins"


def _sync_shared_wire() -> None:
	"""Copy shared/nvda_mcp_wire/protocol.py into the addon package (as scons does)."""
	spec = importlib.util.spec_from_file_location("_sync_shared", _ADDON_ROOT / "sync_shared.py")
	assert spec is not None and spec.loader is not None
	module = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(module)
	module.sync()


_sync_shared_wire()
if str(_GLOBAL_PLUGINS) not in sys.path:
	sys.path.insert(0, str(_GLOBAL_PLUGINS))

# Imported after the bootstrap above on purpose: `fakes` imports the addon
# package, which is only importable once globalPlugins is on sys.path.
from fakes import FakeClock  # noqa: E402


@pytest.fixture
def clock() -> FakeClock:
	"""The session-wide fake clock; time moves only when a test says so.

	Anything that reads time or waits takes the Clock port, so handing tests one
	shared fake here means every collaborator built from it agrees on "now" by
	construction, rather than each test re-wiring that relationship by hand.
	"""
	return FakeClock()
