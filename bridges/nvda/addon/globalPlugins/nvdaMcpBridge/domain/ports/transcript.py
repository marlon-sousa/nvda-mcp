# nvdaMcpBridge domain -- the Transcript port.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# ROLE: the human-readable record of everything a session did.
# USED BY: the Session controller (it reports each event as it happens).
# IMPLEMENTED BY: adapters/file_transcript.py (timestamped lines on disk);
#                 tests/fakes/transcript.py FakeTranscript (records in memory).
#
# Silent-mode runs are an audio blackout: nobody hears what NVDA "said", so the
# transcript is how a tester reconstructs the run afterwards. It is written
# bridge-side -- complete even if the agent never fetched some speech -- and
# ``path`` is handed to the agent at ``hello`` so the server can surface it.
#
# The domain says WHAT happened; how it is rendered and where it lands are the
# adapter's business.

from __future__ import annotations

from abc import ABC, abstractmethod


class Transcript(ABC):
	"""A per-session record of session events, in order."""

	@property
	@abstractmethod
	def path(self) -> str:
		"""Where the record can be read; returned to the agent at ``hello``."""

	@abstractmethod
	def open(self) -> None: ...

	@abstractmethod
	def session_opened(self, mode: str, synth: str) -> None: ...

	@abstractmethod
	def gesture(self, gesture_id: str) -> None: ...

	@abstractmethod
	def speech(self, text: str) -> None: ...

	@abstractmethod
	def note(self, text: str) -> None: ...

	@abstractmethod
	def session_closed(self, reason: str) -> None: ...
