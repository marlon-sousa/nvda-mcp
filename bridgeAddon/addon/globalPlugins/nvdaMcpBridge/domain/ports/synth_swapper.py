# nvdaMcpBridge domain -- the SynthSwapper port.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# ROLE: domain port. The silent-mode synth swap, and the promise to undo it.
# USED BY: the Session controller.
# IMPLEMENTED BY: adapters/nvda_synth_swapper.py in session C (the whole
#                 fail-safe defence of RFC 0001: config agreement, the
#                 pre_configSave guard, the getSynthInstance patch);
#                 tests/fakes/synth_swapper.py FakeSynthSwapper.
#
# This port owns the bridge's non-negotiable invariant (AGENTS.md #3): a crashed
# harness must never leave a blind user mute. That is why :meth:`restore` is
# idempotent -- the Session calls it in ``finally`` on EVERY teardown path,
# whether or not a swap ever happened, and calling it twice is harmless.

from __future__ import annotations

from abc import ABC, abstractmethod


class SynthSwapper(ABC):
	"""Swaps NVDA's synth for the spy (silent mode) and always restores it."""

	@abstractmethod
	def current_synth(self) -> str:
		"""Name of the user's real synth -- reported at ``hello`` in either mode."""

	@abstractmethod
	def swap_to_spy(self) -> str:
		"""Install the spy synth for the session; return the real synth's name.

		Silent mode only. Performs the entire fail-safe defence so the swap
		survives config-profile switches and never persists to disk.
		"""

	@abstractmethod
	def restore(self) -> None:
		"""Undo the swap and every guard. Idempotent: safe when nothing was
		swapped, and safe to call more than once."""
