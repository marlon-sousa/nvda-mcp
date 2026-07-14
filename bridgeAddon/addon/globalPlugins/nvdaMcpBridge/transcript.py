# nvdaMcpBridge -- per-session transcript log.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# Silent-mode runs are an audio blackout: nobody hears what NVDA "said". The
# bridge therefore writes a plain-text transcript per session so the tester can
# reconstruct the run afterwards -- one timestamped line per event, gestures
# interleaved with the speech they produced, plus session open/close and the
# synth swap/restore. It is written bridge-side (so it is complete even if the
# agent never fetched some speech) and flushed per line (so a crash loses
# nothing). The ``hello`` response returns the path so the server can surface it.

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Callable

#: Default number of recent session logs to retain; older ones are pruned.
DEFAULT_KEEP: int = 20


def _wallclock() -> str:
	return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


class TranscriptLog:
	"""Append-only, line-flushed transcript for one session.

	Timestamps come from an injectable callable (defaulting to wall-clock) so
	tests get deterministic output. All writers are best-effort: a logging
	failure must never take down a session (and certainly never block synth
	restoration), so write errors are swallowed after the file is opened.
	"""

	def __init__(self, path: str | os.PathLike[str], *, timestamp: Callable[[], str] = _wallclock) -> None:
		self._path = Path(path)
		self._timestamp = timestamp
		self._file: object | None = None

	@property
	def path(self) -> str:
		return str(self._path)

	def open(self) -> None:
		"""Create/truncate the log file and ready it for line-buffered writes."""
		self._path.parent.mkdir(parents=True, exist_ok=True)
		self._file = open(self._path, "w", encoding="utf-8", buffering=1)

	def _line(self, text: str) -> None:
		f = self._file
		if f is None:
			return
		try:
			f.write(f"{self._timestamp()} {text}\n")  # type: ignore[attr-defined]
			f.flush()  # type: ignore[attr-defined]
		except OSError:
			pass

	def session_opened(self, mode: str, synth: str) -> None:
		self._line(f"SESSION OPEN mode={mode} synth={synth}")

	def synth_swapped(self, real_synth: str) -> None:
		self._line(f"SYNTH SWAP in=nvdaMcpSpy saved={real_synth}")

	def synth_restored(self, real_synth: str) -> None:
		self._line(f"SYNTH RESTORE -> {real_synth}")

	def gesture(self, gesture_id: str) -> None:
		self._line(f"GESTURE {gesture_id}")

	def speech(self, text: str) -> None:
		self._line(f"SPEECH {text!r}")

	def note(self, text: str) -> None:
		self._line(f"NOTE {text}")

	def session_closed(self, reason: str) -> None:
		self._line(f"SESSION CLOSE reason={reason}")
		f = self._file
		self._file = None
		if f is not None:
			try:
				f.close()  # type: ignore[attr-defined]
			except OSError:
				pass


def create_session_log(
	logs_dir: str | os.PathLike[str],
	*,
	keep: int = DEFAULT_KEEP,
	timestamp: Callable[[], str] = _wallclock,
	name_stamp: Callable[[], str] | None = None,
) -> TranscriptLog:
	"""Open a fresh ``session-<stamp>.log`` under ``logs_dir``, pruning old ones.

	``name_stamp`` builds the filename component (defaults to a filesystem-safe
	wall-clock stamp); ``keep`` bounds how many ``session-*.log`` files survive,
	oldest deleted first. Returns an opened :class:`TranscriptLog`.
	"""
	directory = Path(logs_dir)
	directory.mkdir(parents=True, exist_ok=True)
	stamp = (name_stamp or (lambda: datetime.now().strftime("%Y%m%d-%H%M%S-%f")))()
	log = TranscriptLog(directory / f"session-{stamp}.log", timestamp=timestamp)
	log.open()
	_prune(directory, keep)
	return log


def _prune(directory: Path, keep: int) -> None:
	# Names embed a time-sortable stamp, so a lexical sort is a chronological
	# one -- and, unlike mtime, is stable when files land in the same millisecond.
	existing = sorted(directory.glob("session-*.log"), key=lambda p: p.name)
	for stale in existing[: max(0, len(existing) - keep)]:
		try:
			stale.unlink()
		except OSError:
			pass
