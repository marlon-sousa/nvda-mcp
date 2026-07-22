# nvdaMcpBridge tests -- FakeAnnouncer, standing in for the Announcer port.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# FAKES: domain/ports/announcer.py
#
# Reports a fixed synth name (what hello echoes) and records the hints the
# announce command asked to speak.

from __future__ import annotations

from nvdaMcpBridge.domain.ports.announcer import Announcer


class FakeAnnouncer(Announcer):
	"""Records announced hints and reports a scripted synth name."""

	def __init__(self, synth: str = "espeak") -> None:
		self._synth = synth
		self.announced: list[str] = []

	def current_synth(self) -> str:
		return self._synth

	def announce(self, text: str) -> None:
		self.announced.append(text)
