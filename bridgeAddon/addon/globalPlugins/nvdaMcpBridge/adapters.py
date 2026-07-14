# nvdaMcpBridge -- adapter interfaces (ports) for the bridge core.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# The bridge core (session state machine, speech buffer, framing, transcript)
# is stdlib-only and unit-tested headlessly under desktop Python. Every touch
# of NVDA is confined behind the narrow *adapter interfaces* declared here, and
# implemented for real in ``nvda_adapters.py`` (session C, the only module that
# imports ``speech`` / ``synthDriverHandler`` / ``inputCore`` / ``config``).
# The fakes in ``tests/fakes.py`` implement the same Protocols so the whole
# state machine can be exercised without NVDA -- including "after a simulated
# profile switch the spy is still active and restore still ran".
#
# There are four adapters, matching the spec's ports-and-adapters split:
#   * Clock          -- monotonic time + sleep, so wait logic is deterministic.
#   * SpeechSource    -- owns the speech/braille capture lifecycle + buffers.
#   * SynthSwapper    -- the whole silent-mode synth defence (swap + restore).
#   * GestureSender   -- emulate an NVDA gesture, blocking until processed.

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
	from .speech_buffer import BrailleBuffer, SpeechBuffer


@runtime_checkable
class Clock(Protocol):
	"""Monotonic clock + sleep, injected everywhere time is read or waited on.

	Real code uses :class:`RealClock`; tests use a fake that advances only when
	told, so timeout/heartbeat/inactivity behaviour is exercised without ever
	sleeping in real time.
	"""

	def monotonic(self) -> float:
		"""Seconds from an arbitrary fixed origin; only differences are meaningful."""
		...

	def sleep(self, seconds: float) -> None:
		"""Block for ``seconds`` (fakes may make this an instant clock advance)."""
		...


class RealClock:
	"""The production :class:`Clock`: :func:`time.monotonic` / :func:`time.sleep`."""

	def monotonic(self) -> float:
		return time.monotonic()

	def sleep(self, seconds: float) -> None:
		time.sleep(seconds)


@runtime_checkable
class SpeechSource(Protocol):
	"""Owns speech/braille capture for a session and the buffers it feeds.

	Both buffers exist before a mode is chosen; :meth:`start` is handed the
	session's capture mode (``"silent"`` / ``"live"``) so the source can wire
	the right NVDA hooks and mark the speech buffer's finish semantics
	(silent mode gets an exact ``synthDoneSpeaking`` signal; live mode falls
	back to the elapsed-time heuristic). :meth:`stop` unregisters everything
	and is safe to call more than once.
	"""

	@property
	def speech(self) -> SpeechBuffer: ...

	@property
	def braille(self) -> BrailleBuffer: ...

	def start(self, mode: str) -> None: ...

	def stop(self) -> None: ...


@runtime_checkable
class SynthSwapper(Protocol):
	"""Owns the silent-mode synth swap *and* the full fail-safe restoration.

	In silent mode :meth:`swap_in` installs the spy as the configured synth and
	the three defence layers (config agreement, the ``pre_configSave`` guard,
	the ``getSynthInstance`` patch) so capture survives profile switches without
	persisting the spy to disk. :meth:`restore` reverses all of it and MUST be
	safe on every teardown path -- idempotent, never raising past a best-effort
	attempt to put the user's real synth back. ``real_synth_name`` is the synth
	the user actually had (reported to the agent at ``hello``).
	"""

	@property
	def real_synth_name(self) -> str: ...

	@property
	def swapped(self) -> bool: ...

	def swap_in(self) -> None: ...

	def restore(self) -> None: ...


@runtime_checkable
class GestureSender(Protocol):
	"""Emulates an NVDA keyboard gesture, blocking until it has been processed.

	``gesture_id`` is an NVDA gesture identifier such as ``"NVDA+f7"`` or
	``"control+shift+downArrow"``. Raises :class:`ValueError` for an
	unparseable identifier so the bridge can report a clear wire error.
	"""

	def send(self, gesture_id: str) -> None: ...
