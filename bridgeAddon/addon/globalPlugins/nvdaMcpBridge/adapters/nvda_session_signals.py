# nvdaMcpBridge adapters -- NvdaSessionSignals: the start/end session beeps.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# ROLE: adapter. IMPLEMENTS the SessionSignals port with NVDA's `tones`. On
#       pyright's ignore list (imports NVDA).
# BUILT BY: plugin.py (once) and injected via wiring.build_session.
# USED BY: the Session -- ascending pair when a session establishes, descending
#          pair at teardown. Tones (not speech) so they are heard even in silent
#          mode, when captured speech is suppressed.
#
# Marshalled to NVDA's main thread, like every other NVDA touch here.

from __future__ import annotations

import tones
import wx

from ..domain.ports.session_signals import SessionSignals
from .nvda_main_thread import run_on_main

_LOW_HZ = 440
_HIGH_HZ = 660
_TONE_MS = 180
#: Start-to-start spacing of the two tones. Must exceed _TONE_MS so the first
#: tone finishes (and is audible) before the second starts on the same player --
#: back-to-back beeps swallowed the first.
_GAP_MS = 300


class NvdaSessionSignals(SessionSignals):
	"""Two spaced ascending tones on start, two descending on end."""

	def session_started(self) -> None:
		run_on_main(lambda: self._pair(_LOW_HZ, _HIGH_HZ))

	def session_ended(self) -> None:
		run_on_main(lambda: self._pair(_HIGH_HZ, _LOW_HZ))

	@staticmethod
	def _pair(first_hz: int, second_hz: int) -> None:
		tones.beep(first_hz, _TONE_MS)
		# Schedule the second tone after a gap so the first is fully heard.
		wx.CallLater(_GAP_MS, tones.beep, second_hz, _TONE_MS)
