# nvdaMcpBridge tests -- FakeLogCapture, standing in for the LogCapture port.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# FAKES: domain/ports/log_capture.py
#
# Mirrors FakeTranscript's shape exactly: records each call as a tuple so a
# test asserts exactly what the hello handler / Session teardown did, without
# a real NVDA logger. ``fail_on`` makes a named call raise -- the tool that
# proves teardown finishes even when stopping capture throws mid-teardown.

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from nvdaMcpBridge.domain.ports.log_capture import LogCapture

if TYPE_CHECKING:
	from nvdaMcpBridge import protocol as p


class FakeLogCapture(LogCapture):
	"""An in-memory :class:`LogCapture` that records every call."""

	def __init__(self, path: str = "nvda-log.log", *, fail_on: set[str] | None = None) -> None:
		self._path = path
		self._fail_on = fail_on or set()
		self.events: list[tuple[Any, ...]] = []

	@property
	def path(self) -> str:
		return self._path

	def _record(self, name: str, *args: Any) -> None:
		self.events.append((name, *args))
		if name in self._fail_on:
			raise RuntimeError(f"log capture failing on {name}")

	def start(self, level: p.LogLevel | None) -> None:
		self._record("start", level)

	def stop(self) -> None:
		self._record("stop")
