# nvdaMcpBridge tests -- FakeTranscript, standing in for the Transcript port.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# FAKES: domain/ports/transcript.py
#
# Records each event as a tuple so a test asserts the exact vocabulary the
# Session emitted, in order, without a filesystem. ``fail_on`` makes a named
# event raise -- the tool that proves teardown finishes (and the synth still
# restores) even when the transcript throws mid-teardown.

from __future__ import annotations

from typing import Any

from nvdaMcpBridge.domain.ports.transcript import Transcript


class FakeTranscript(Transcript):
	"""An in-memory :class:`Transcript` that records every event."""

	def __init__(self, path: str = "session.log", *, fail_on: set[str] | None = None) -> None:
		self._path = path
		self._fail_on = fail_on or set()
		self.events: list[tuple[Any, ...]] = []
		self.opened = False

	@property
	def path(self) -> str:
		return self._path

	def _record(self, name: str, *args: Any) -> None:
		self.events.append((name, *args))
		if name in self._fail_on:
			raise RuntimeError(f"transcript failing on {name}")

	def open(self) -> None:
		self.opened = True
		self._record("open")

	def session_opened(self, mode: str, synth: str) -> None:
		self._record("session_opened", mode, synth)

	def synth_swapped(self, real_synth: str) -> None:
		self._record("synth_swapped", real_synth)

	def synth_restored(self, real_synth: str) -> None:
		self._record("synth_restored", real_synth)

	def gesture(self, gesture_id: str) -> None:
		self._record("gesture", gesture_id)

	def speech(self, text: str) -> None:
		self._record("speech", text)

	def note(self, text: str) -> None:
		self._record("note", text)

	def session_closed(self, reason: str) -> None:
		self._record("session_closed", reason)
