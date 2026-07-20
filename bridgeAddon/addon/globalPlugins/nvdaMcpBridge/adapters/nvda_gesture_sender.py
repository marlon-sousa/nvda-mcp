# nvdaMcpBridge adapters -- NvdaGestureSender: inject a keypress the way NVDA sees one.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# ROLE: adapter. IMPLEMENTS the GestureSender port. On pyright's ignore list
#       (imports NVDA); validated by the 9c live-NVDA checklist (item 2).
# BUILT BY: adapters/nvda_adapter_factory.py.
# USED BY: the Session, answering pressGesture.
#
# Two NVDA facts shape this. (1) A gesture must be emulated on NVDA's MAIN
# thread; the session runs on the server thread, so we marshal via wx.CallAfter
# and block on an Event until the main thread is done. (2) emulateGesture ->
# InputGesture.send injects the key and waits on NVDA's own _injectionDoneEvent
# (keyboardHandler.py:696-699), so once CallAfter returns the keypress has really
# reached NVDA. An unknown key name or an emulation failure becomes a
# GestureError -- a per-command failure the Session reports, not a session death.

from __future__ import annotations

import threading

import inputCore
import wx
from keyboardHandler import KeyboardInputGesture

from ..domain.ports.gesture_sender import GestureError, GestureSender

#: Upper bound on how long press() waits for the main thread to emulate the
#: gesture before giving up -- generous, since it only trips on a wedged UI.
DEFAULT_GESTURE_TIMEOUT: float = 10.0


class NvdaGestureSender(GestureSender):
	"""Emulates a keyboard gesture on NVDA's main thread and blocks until done."""

	def __init__(self, *, timeout: float = DEFAULT_GESTURE_TIMEOUT) -> None:
		self._timeout = timeout

	def press(self, gesture_id: str) -> None:
		try:
			gesture = KeyboardInputGesture.fromName(gesture_id)
		except Exception as exc:
			raise GestureError(f"unknown gesture id {gesture_id!r}: {exc}") from exc

		done = threading.Event()
		failure: list[BaseException] = []

		def _emulate() -> None:
			try:
				inputCore.manager.emulateGesture(gesture)
			except Exception as exc:  # noqa: BLE001 -- reported back as a GestureError
				failure.append(exc)
			finally:
				done.set()

		wx.CallAfter(_emulate)
		if not done.wait(self._timeout):
			raise GestureError(f"gesture {gesture_id!r} timed out after {self._timeout}s")
		if failure:
			raise GestureError(f"gesture {gesture_id!r} failed: {failure[0]}") from failure[0]
