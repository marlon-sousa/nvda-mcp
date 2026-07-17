# nvdaMcpBridge tests -- FakeGestureSender, standing in for the GestureSender port.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# FAKES: domain/ports/gesture_sender.py
#
# The fake-NVDA core. In production, pressing a key makes NVDA speak, and that
# speech flows through the speech source into the buffer -- the gesture sender
# never touches the buffer itself. This fake reproduces that causal chain for a
# test: it is given a gesture -> speech script and the FakeSpeechSource, and on a
# scripted press it feeds those lines into that source's buffer, so the whole
# "press, then read what it said" path runs through the real Session. ``reject``
# ids raise GestureError, to drive the pressGesture error path.

from __future__ import annotations

from typing import TYPE_CHECKING, Mapping, Sequence

from nvdaMcpBridge.domain.ports.gesture_sender import GestureError, GestureSender

if TYPE_CHECKING:
	from .speech_source import FakeSpeechSource


class FakeGestureSender(GestureSender):
	"""Records presses; optionally rejects ids and/or speaks a scripted response."""

	def __init__(
		self,
		source: FakeSpeechSource,
		*,
		reject: Sequence[str] | None = None,
		speech: Mapping[str, Sequence[str]] | None = None,
	) -> None:
		self._source = source
		self._reject = set(reject or ())
		self._speech = {gid: list(lines) for gid, lines in (speech or {}).items()}
		self.pressed: list[str] = []
		#: Ids that raise an UNEXPECTED (non-GestureError) exception, to drive the
		#: Session's generic "a handler blew up" recovery path.
		self.boom: set[str] = set()

	def press(self, gesture_id: str) -> None:
		if gesture_id in self._reject:
			raise GestureError(f"unknown gesture: {gesture_id!r}")
		if gesture_id in self.boom:
			raise RuntimeError(f"unexpected fault pressing {gesture_id!r}")
		self.pressed.append(gesture_id)
		lines = self._speech.get(gesture_id)
		if not lines:
			return
		buffer = self._source.buffer
		assert buffer is not None, "a scripted gesture spoke before the source was started"
		for line in lines:
			buffer.append([line])
		buffer.notify_finished()
