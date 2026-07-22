# nvdaMcpBridge adapters -- NvdaLogCapture: tees NVDA's log for one session.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# ROLE: adapter. IMPLEMENTS the LogCapture domain port with NVDA's own logging
#       machinery. On pyright's ignore list (imports NVDA via `logHandler`);
#       validated by the live-NVDA checklist (spec 0009), not the type checker.
# BUILT BY: plugin.py (once, like NvdaSessionSignals/NvdaAnnouncer) and injected
#           via wiring.build_session.
# USED BY: the hello handler (start, with the requested level) and the
#          Session's teardown (stop, unconditionally).
#
# A reused singleton, not built fresh per connection: the bridge serves one
# session at a time (AGENTS.md), so start()/stop() simply reset this instance's
# per-session state each time, the same way NvdaSessionSignals is stateless
# across sessions.
#
# NVDA installs its own file handler and level on `log.root` (the actual root
# logger), not on the "nvda" logger `log` itself -- `logHandler._setupLogging`
# does `log.root.addHandler(...)` / `log.root.setLevel(...)`, because `log` is
# a named child logger left at NOTSET, inheriting its effective level from the
# root. A second handler or a level change placed on `log` instead would
# silently see nothing change (Logger.isEnabledFor is what gates emission in
# the first place, and it walks up to `log.root` for the effective level). So
# this mirrors NVDA's own placement exactly.

from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from logHandler import Formatter, log

from ..domain.ports.log_capture import LogCapture

if TYPE_CHECKING:
	from .. import protocol

#: Default number of recent capture files to retain; older ones are pruned.
DEFAULT_KEEP: int = 20

#: NVDA's own log line format (logHandler._setupLogging), so a capture file
#: reads like a slice of nvda.log, not a foreign format.
_FORMAT = "{levelname!s} - {codepath!s} ({asctime}) - {threadName} ({thread}):\n{message}"


class NvdaLogCapture(LogCapture):
	"""Tees NVDA's log to a fresh per-session file, optionally at a bumped level."""

	def __init__(
		self,
		logs_dir: str | os.PathLike[str],
		*,
		keep: int = DEFAULT_KEEP,
		name_stamp: Callable[[], str] | None = None,
	) -> None:
		self._dir = Path(logs_dir)
		self._keep = keep
		self._name_stamp = name_stamp or (lambda: datetime.now().strftime("%Y%m%d-%H%M%S-%f"))
		self._path: str | None = None
		self._handler: logging.FileHandler | None = None
		self._previous_level: int | None = None

	@property
	def path(self) -> str:
		assert self._path is not None, "path read before start()"
		return self._path

	def start(self, level: protocol.LogLevel | None) -> None:
		self._dir.mkdir(parents=True, exist_ok=True)
		target = self._dir / f"nvda-log-{self._name_stamp()}.log"
		handler = logging.FileHandler(target, encoding="utf-8")
		handler.setFormatter(Formatter(fmt=_FORMAT, style="{"))
		self._previous_level = log.root.level
		if level is not None:
			log.root.setLevel(getattr(log, level.name))
		log.root.addHandler(handler)
		self._handler = handler
		self._path = str(target)
		_prune(self._dir, self._keep)

	def stop(self) -> None:
		if self._handler is None:
			return
		log.root.removeHandler(self._handler)
		self._handler.close()
		self._handler = None
		if self._previous_level is not None:
			log.root.setLevel(self._previous_level)
			self._previous_level = None


def _prune(directory: Path, keep: int) -> None:
	# A distinct prefix from the transcript's `session-*.log`, so each stack's
	# pruning only ever touches its own files.
	existing = sorted(directory.glob("nvda-log-*.log"), key=lambda p: p.name)
	for stale in existing[: max(0, len(existing) - keep)]:
		try:
			stale.unlink()
		except OSError:
			pass
