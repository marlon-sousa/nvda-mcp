# nvdaMcpBridge adapters -- NvdaSynthSwapper: the silent-mode synth swap + restore.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# ROLE: adapter. IMPLEMENTS the SynthSwapper port -- the whole Decided fail-safe
#       defence of RFC 0001 (spec 0007). On pyright's ignore list (imports NVDA);
#       validated by the 9c live-NVDA checklist (fail-safe items 2-3, 6).
# BUILT BY: adapters/nvda_adapter_factory.py.
# USED BY: the Session, which calls restore() in a finally on EVERY teardown path.
#
# The invariant this file exists to keep (AGENTS.md #3): a crashed harness must
# never leave a blind user mute. So restore() is idempotent and unconditional.
#
# Why three layers, not just setSynth (learned from reading 2026.1 source):
# synthDriverHandler reloads config["speech"]["synth"] on every
# post_configProfileSwitch, and profile switches are frequent. So swapping alone
# (isFallback=True, which leaves config naming the real synth) is self-defeating:
# the first profile switch reconciles config against the loaded synth and rips
# the spy out. Instead, for the session only:
#   1. make config name the spy, so the reconciliation is a no-op;
#   2. guard config SAVE (pre -> real name on disk, post -> spy back in memory),
#      so the spy never persists past the session;
#   3. patch getSynthInstance, so a profile that stores a different synth still
#      loads the spy -- capture survives with no audio blip.
# restore() reverses all three, in the reverse order, and is safe if nothing was
# ever swapped.

from __future__ import annotations

from typing import Any, Callable

import config
import synthDriverHandler

from ..domain.ports.synth_swapper import SynthSwapper
from . import spy_sink


class NvdaSynthSwapper(SynthSwapper):
	"""Installs the spy synth for a silent session and always restores the user's."""

	def __init__(self) -> None:
		self._real_synth: str | None = None
		self._orig_get_synth_instance: Callable[..., Any] | None = None

	def current_synth(self) -> str:
		synth = synthDriverHandler.getSynth()
		return synth.name if synth is not None else ""

	def swap_to_spy(self) -> str:
		real = self.current_synth()
		self._real_synth = real

		# Layer 3 first: patch getSynthInstance BEFORE setSynth, so the load below
		# (and any concurrent profile switch) already resolves to the spy.
		self._orig_get_synth_instance = synthDriverHandler.getSynthInstance
		synthDriverHandler.getSynthInstance = self._patched_get_synth_instance

		# Layer 1: make NVDA load the spy and make config agree, so a later
		# post_configProfileSwitch reconciliation is a no-op rather than a teardown.
		synthDriverHandler.setSynth(spy_sink.SPY_SYNTH_NAME)
		config.conf["speech"]["synth"] = spy_sink.SPY_SYNTH_NAME

		# Layer 2: keep the spy out of any config the user saves mid-session.
		config.pre_configSave.register(self._on_pre_config_save)
		config.post_configSave.register(self._on_post_config_save)
		return real

	def restore(self) -> None:
		if self._real_synth is None:
			return  # nothing was swapped; idempotent no-op
		real = self._real_synth
		self._real_synth = None

		config.pre_configSave.unregister(self._on_pre_config_save)
		config.post_configSave.unregister(self._on_post_config_save)

		if self._orig_get_synth_instance is not None:
			synthDriverHandler.getSynthInstance = self._orig_get_synth_instance
			self._orig_get_synth_instance = None

		config.conf["speech"]["synth"] = real
		synthDriverHandler.setSynth(real)

	# -- the guards ----------------------------------------------------------

	def _patched_get_synth_instance(self, name: str, asDefault: bool = False) -> Any:
		# Ignore the requested name: whatever NVDA tries to load, it gets the spy,
		# so a synth-changing profile cannot displace capture mid-session.
		assert self._orig_get_synth_instance is not None
		return self._orig_get_synth_instance(spy_sink.SPY_SYNTH_NAME, asDefault)

	def _on_pre_config_save(self) -> None:
		# Write the user's real synth to the file being saved...
		config.conf["speech"]["synth"] = self._real_synth

	def _on_post_config_save(self) -> None:
		# ...then put the spy back in the live config so capture continues.
		if self._real_synth is not None:
			config.conf["speech"]["synth"] = spy_sink.SPY_SYNTH_NAME
