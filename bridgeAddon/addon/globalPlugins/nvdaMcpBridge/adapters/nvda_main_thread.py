# nvdaMcpBridge adapters -- run_on_main: marshal a call onto NVDA's wx main thread.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# ROLE: a tiny shared edge helper (imports wx), on pyright's ignore list.
# USED BY: the NVDA adapters that mutate NVDA (tones, the synth) from the bridge's
#          server thread -- NVDA does that work on its main thread, so touching it
#          off-thread races NVDA (the silent-mode mute bug was exactly this).
#
# Fire-and-forget by default (the caller does not need a result and must never
# deadlock a main-thread caller); `block=True` waits for the result when the
# caller needs it and is known to be off the main thread with the main thread free.

from __future__ import annotations

import threading
from typing import Any, Callable, TypeVar

import wx

_T = TypeVar("_T")

_MAIN_THREAD_TIMEOUT: float = 10.0


def run_on_main(func: Callable[[], _T], *, block: bool = False) -> _T | None:
	"""Run ``func`` on NVDA's main thread; return its result when ``block``."""
	if wx.IsMainThread():
		return func()
	if not block:
		try:
			wx.CallAfter(func)
		except Exception:
			pass  # wx gone (NVDA shutting down): nothing to do
		return None
	done = threading.Event()
	box: dict[str, Any] = {}

	def runner() -> None:
		try:
			box["value"] = func()
		except BaseException as exc:
			box["error"] = exc
		finally:
			done.set()

	wx.CallAfter(runner)
	if not done.wait(_MAIN_THREAD_TIMEOUT):
		raise TimeoutError("timed out marshaling to NVDA's main thread")
	if "error" in box:
		raise box["error"]
	return box.get("value")
