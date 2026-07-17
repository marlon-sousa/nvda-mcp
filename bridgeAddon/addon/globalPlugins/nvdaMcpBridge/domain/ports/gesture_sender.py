# nvdaMcpBridge domain -- the GestureSender port.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# ROLE: domain port. Injects a keyboard gesture and blocks until NVDA processed it.
# USED BY: the Session controller (answering pressGesture).
# IMPLEMENTED BY: adapters/nvda_gesture_sender.py in session C (the emulateKeyPress
#                 port from NVDA's own speechSpyGlobalPlugin);
#                 tests/fakes/gesture_sender.py FakeGestureSender.
#
# GestureError is part of this port's contract, so it lives here: an unknown or
# rejected gesture id is a normal, per-command failure the Session reports and
# recovers from, not a session-ending fault.

from __future__ import annotations

from abc import ABC, abstractmethod


class GestureError(Exception):
	"""An gesture id could not be resolved or emulated (e.g. an unknown key name)."""


class GestureSender(ABC):
	"""Emulates a keyboard gesture the way a real keypress reaches NVDA."""

	@abstractmethod
	def press(self, gesture_id: str) -> None:
		"""Emulate ``gesture_id`` (e.g. ``"NVDA+f7"``) and block until processed.

		Raises :class:`GestureError` if the id is unknown or NVDA rejects it.
		"""
