# nvdaMcpBridge adapters -- spy_sink: the spy synth <-> speech source rendezvous.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# ROLE: a supporting construct -- a pure module-level rendezvous, no NVDA import,
#       so it stays strict-checked and unit-tested (unlike the nvda_*.py edge).
# WRITTEN TO: synthDrivers/nvdaMcpSpy.py -- the spy synth NVDA instantiates (never
#             our wiring) -- calls notify() with each spoken sequence's text.
# READ BY: adapters/nvda_spy_speech_source.py, which registers the current sink
#          (feeding the SpeechBuffer) at hello and clears it at teardown.
#
# Why a module-level rendezvous at all: the spy synth is constructed by NVDA's
# synthDriverHandler, not by our AdapterFactory, so the two cannot be handed each
# other at wiring time. This module is the fixed meeting point they both import
# by name -- exactly one sink at a time (one session at a time, by BridgeServer).
# It holds no NVDA types (just str chunks), so it is the seam that keeps the
# capture path testable while the synth driver itself stays an untested edge.

from __future__ import annotations

from typing import Callable, Sequence

#: The spy synth's driver name. Defined here, in the one strict-checked file both
#: the driver and the speech source import, so setSynth("nvdaMcpSpy") and the
#: synthDoneSpeaking filter cannot drift apart.
SPY_SYNTH_NAME: str = "nvdaMcpSpy"

#: A sink takes the plain-text chunks of one spoken sequence.
Sink = Callable[[Sequence[str]], None]

_sink: Sink | None = None


def set_sink(sink: Sink) -> None:
	"""Register the sink notify() delivers to (the active session's speech source)."""
	global _sink
	_sink = sink


def clear_sink() -> None:
	"""Drop the sink; notify() becomes a no-op. Idempotent."""
	global _sink
	_sink = None


def notify(text_chunks: Sequence[str]) -> None:
	"""Deliver one sequence's text to the registered sink, if any.

	Called from NVDA's speech thread (the spy synth's ``speak``). Reads the sink
	into a local first, so a concurrent :func:`clear_sink` cannot turn it into a
	``None`` call between the check and the invocation.
	"""
	sink = _sink
	if sink is not None:
		sink(text_chunks)
