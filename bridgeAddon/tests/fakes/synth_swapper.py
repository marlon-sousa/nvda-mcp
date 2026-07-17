# nvdaMcpBridge tests -- FakeSynthSwapper, standing in for the SynthSwapper port.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# FAKES: domain/ports/synth_swapper.py
#
# Records the swap/restore call ORDER, because the invariant under test is a
# sequence ("restore ran on this teardown path", "restore is idempotent"), not a
# value. ``fail_restore`` makes restore raise, so a test can prove teardown's
# guard keeps going -- the channel still closes even when the restore throws.

from __future__ import annotations

from nvdaMcpBridge.domain.ports.synth_swapper import SynthSwapper


class FakeSynthSwapper(SynthSwapper):
	"""Records swap/restore calls; can be told to fail its restore."""

	def __init__(self, synth: str = "espeak", *, fail_restore: bool = False) -> None:
		self._synth = synth
		self._fail_restore = fail_restore
		self.calls: list[str] = []

	@property
	def swaps(self) -> int:
		return self.calls.count("swap")

	@property
	def restores(self) -> int:
		return self.calls.count("restore")

	def current_synth(self) -> str:
		self.calls.append("current")
		return self._synth

	def swap_to_spy(self) -> str:
		self.calls.append("swap")
		return self._synth

	def restore(self) -> None:
		self.calls.append("restore")
		if self._fail_restore:
			raise RuntimeError("restore failed")
