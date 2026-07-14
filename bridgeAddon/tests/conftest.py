# Headless test harness for the bridge core (session B).
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# The bridge core is stdlib-only and imports NVDA nowhere, but it lives inside
# the ``nvdaMcpBridge`` global-plugin package whose ``__init__`` (the inert
# plugin skeleton) does import a couple of NVDA modules at load time. To import
# the core modules headlessly we therefore: (1) sync the shared wire module in
# so ``from . import protocol`` resolves to the exact shipped bytes; (2) stub
# the handful of NVDA modules the package ``__init__`` touches; (3) put the
# ``globalPlugins`` directory on ``sys.path`` so ``import nvdaMcpBridge.*`` works.
#
# Pyright, by contrast, resolves the real NVDA modules from ../nvda/source, so
# the stubs here are runtime-only and never affect type checking.

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

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


def _stub_nvda_modules() -> None:
	"""Provide just enough of NVDA for the inert plugin ``__init__`` to import."""
	if "globalPluginHandler" not in sys.modules:
		gph = types.ModuleType("globalPluginHandler")

		class GlobalPlugin:  # minimal stand-in for the NVDA base class
			def __init__(self) -> None:
				pass

			def terminate(self) -> None:
				pass

		gph.GlobalPlugin = GlobalPlugin  # type: ignore[attr-defined]
		sys.modules["globalPluginHandler"] = gph

	if "logHandler" not in sys.modules:
		lh = types.ModuleType("logHandler")

		class _Log:
			def debug(self, *args: object, **kwargs: object) -> None: ...
			def info(self, *args: object, **kwargs: object) -> None: ...
			def warning(self, *args: object, **kwargs: object) -> None: ...
			def error(self, *args: object, **kwargs: object) -> None: ...

		lh.log = _Log()  # type: ignore[attr-defined]
		sys.modules["logHandler"] = lh


_sync_shared_wire()
_stub_nvda_modules()
if str(_GLOBAL_PLUGINS) not in sys.path:
	sys.path.insert(0, str(_GLOBAL_PLUGINS))
