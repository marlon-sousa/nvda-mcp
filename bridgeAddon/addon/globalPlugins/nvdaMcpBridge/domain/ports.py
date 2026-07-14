# nvdaMcpBridge domain -- the ports (abstract interfaces the domain depends on).
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# These are the seams of the hexagon. The domain (session state machine, speech
# buffers, framing) is written against these ABCs and nothing else; the
# ``adapters/`` package provides one concrete subclass of each (NVDA-backed in
# production, in-memory fakes in tests), and ``wiring.py`` is the only place
# that binds the two together.
#
# They are ``abc.ABC`` with ``@abstractmethod`` -- not ``typing.Protocol`` -- on
# purpose: an adapter that forgets a method fails loudly at construction, and
# the interface itself can never be instantiated.

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
	from .. import protocol as p
	from .speech_buffer import BrailleBuffer, SpeechBuffer


class Clock(ABC):
	"""Monotonic time + sleep, injected wherever time is read or waited on.

	Fakes advance only when told, so timeout/heartbeat/inactivity behaviour is
	exercised without ever sleeping in real time.
	"""

	@abstractmethod
	def monotonic(self) -> float:
		"""Seconds from an arbitrary fixed origin; only differences matter."""

	@abstractmethod
	def sleep(self, seconds: float) -> None:
		"""Block for ``seconds`` (a fake may make this an instant clock advance)."""


class Transport(ABC):
	"""The raw byte pipe a :class:`~..domain.framing.Connection` frames over.

	``recv`` returns the next chunk, ``b""`` at EOF, and raises ``TimeoutError``
	when no data arrived within its poll window (a real socket set with
	``settimeout`` already behaves exactly this way). The timeout is how the
	session periodically regains control to check its deadlines.
	"""

	@abstractmethod
	def recv(self) -> bytes: ...

	@abstractmethod
	def sendall(self, data: bytes) -> None: ...

	@abstractmethod
	def close(self) -> None: ...


class SpeechSource(ABC):
	"""Owns speech/braille capture for a session and the buffers it feeds.

	The concrete source is already built for its mode (silent vs live) by the
	:class:`AdapterFactory`, so :meth:`start` takes no mode: it simply registers
	the NVDA hooks and begins feeding the buffers, and :meth:`stop` unregisters
	(safe to call more than once). The buffers exist for the life of the source.
	"""

	@property
	@abstractmethod
	def speech(self) -> SpeechBuffer: ...

	@property
	@abstractmethod
	def braille(self) -> BrailleBuffer: ...

	@abstractmethod
	def start(self) -> None: ...

	@abstractmethod
	def stop(self) -> None: ...


class SynthSwapper(ABC):
	"""Owns the silent-mode synth swap *and* the full fail-safe restoration.

	``swap_in`` installs the spy as the configured synth plus the three defence
	layers (config agreement, the ``pre_configSave`` guard, the
	``getSynthInstance`` patch). ``restore`` reverses all of it and MUST be safe
	on every teardown path -- idempotent, never raising past a best-effort
	attempt to put the user's real synth back. In live mode the factory supplies
	a no-op swapper so the session's teardown stays uniform.
	"""

	@property
	@abstractmethod
	def real_synth_name(self) -> str: ...

	@property
	@abstractmethod
	def swapped(self) -> bool: ...

	@abstractmethod
	def swap_in(self) -> None: ...

	@abstractmethod
	def restore(self) -> None: ...


class GestureSender(ABC):
	"""Emulates an NVDA keyboard gesture, blocking until it is processed.

	``gesture_id`` is an NVDA identifier such as ``"NVDA+f7"`` or
	``"control+shift+downArrow"``. Raises :class:`ValueError` for an
	unparseable identifier so the bridge can report a clear wire error.
	"""

	@abstractmethod
	def send(self, gesture_id: str) -> None: ...


class Transcript(ABC):
	"""A per-session, line-flushed transcript of everything that happened.

	Written bridge-side (complete even if the agent never fetched some speech)
	and flushed per line (a crash loses nothing). ``path`` is returned to the
	agent at ``hello`` so the server can surface it.
	"""

	@property
	@abstractmethod
	def path(self) -> str: ...

	@abstractmethod
	def open(self) -> None: ...

	@abstractmethod
	def session_opened(self, mode: str, synth: str) -> None: ...

	@abstractmethod
	def synth_swapped(self, real_synth: str) -> None: ...

	@abstractmethod
	def synth_restored(self, real_synth: str) -> None: ...

	@abstractmethod
	def gesture(self, gesture_id: str) -> None: ...

	@abstractmethod
	def speech(self, text: str) -> None: ...

	@abstractmethod
	def note(self, text: str) -> None: ...

	@abstractmethod
	def session_closed(self, reason: str) -> None: ...


@dataclass
class AdapterSet:
	"""The session-scoped, mode-specific adapters the factory hands back."""

	speech_source: SpeechSource
	synth_swapper: SynthSwapper
	gesture_sender: GestureSender


class AdapterFactory(ABC):
	"""Builds the mode-specific adapter set once the handshake reveals the mode.

	This is the injection seam that keeps mode out of construction order: the
	composition root wires a factory, and only after reading ``hello`` does the
	session ask it to build the silent- or live-mode adapters. The real factory
	(session C) builds NVDA-backed adapters; the test factory builds fakes.
	"""

	@abstractmethod
	def build(self, mode: p.CaptureMode) -> AdapterSet: ...
