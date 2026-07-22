# nvdaMcpBridge domain -- the LogCapture port.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# ROLE: a private, session-scoped tee of NVDA's own diagnostic log -- distinct
# from the Transcript (spec 0003), which is the bridge's own domain vocabulary.
# USED BY: the hello handler (start, with the requested level) and the Session
# (stop, unconditionally, in teardown).
# IMPLEMENTED BY: adapters/nvda_log_capture.py (a real tee on NVDA's logger);
#                 tests/fakes/log_capture.py FakeLogCapture (records in memory).
#
# Debugging an add-on today means a manual ritual: mark nvda.log, run the
# repro, mark again, copy the slice out. This automates that: every session
# gets a fresh file scoped to exactly its own hello-to-teardown window, so
# there is no haystack to search. ``path`` is handed to the agent at ``hello``
# (spec 0009).
#
# ``start`` is always called (capture is on for every session); the optional
# level is a temporary, real change to NVDA's own logging -- not a filter
# private to the capture file -- because a logger only hands a record to any
# handler once it has decided to emit it at all. ``stop`` restores whatever
# level was in effect before ``start`` and must be safe to call even if
# ``start`` was never reached (teardown calls it unconditionally, like the
# transcript's ``session_closed``).

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
	from ... import protocol


class LogCapture(ABC):
	"""A per-session tee of NVDA's own log, with an optional temporary level."""

	@property
	@abstractmethod
	def path(self) -> str:
		"""Where the capture can be read; returned to the agent at ``hello``."""

	@abstractmethod
	def start(self, level: protocol.LogLevel | None) -> None: ...

	@abstractmethod
	def stop(self) -> None: ...
