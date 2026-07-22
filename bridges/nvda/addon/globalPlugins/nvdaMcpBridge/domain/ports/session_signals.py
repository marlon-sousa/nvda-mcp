# nvdaMcpBridge domain -- the SessionSignals port.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# ROLE: domain port. Audible, non-speech cues for the human at the keyboard that
#       the bridge has taken / released control of NVDA -- so they land even in
#       silent mode, when speech is captured and inaudible.
# USED BY: the Session controller (start of an established session, and teardown).
# IMPLEMENTED BY: adapters/nvda_session_signals.py (NVDA tones);
#                 tests/fakes/session_signals.py FakeSessionSignals.
#
# Beeps, not speech: they must be heard while the spy is swallowing speech. The
# on/off toggle is entry 9.1's config dialog; the default is on.

from __future__ import annotations

from abc import ABC, abstractmethod


class SessionSignals(ABC):
	"""Audible cues marking when the bridge starts and stops controlling NVDA."""

	@abstractmethod
	def session_started(self) -> None:
		"""Two ascending tones: a session is now controlling NVDA."""

	@abstractmethod
	def session_ended(self) -> None:
		"""Two descending tones: control has been released."""
