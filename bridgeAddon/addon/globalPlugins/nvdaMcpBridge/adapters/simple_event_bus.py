# nvdaMcpBridge adapters -- SimpleEventBus: an in-process, thread-safe event bus.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# ROLE: LEAF adapter. IMPLEMENTS the EventBus port. subscribe() returns a
#       UUID token; unsubscribe(token) removes it. Handlers are stored as
#       weakrefs so a destroyed subscriber is skipped and cleaned up on the
#       next emit — no leak, even if the token is never passed to unsubscribe.
#       A threading.Lock guards all data-structure access because emit() can
#       be called from the server thread while subscribe/unsubscribe run on
#       the main thread (the dialog).
#       No decisions — no unit test file.
# USED BY: plugin.py (builds one, hands it to BridgeServer and the dialog).
# BUILT BY: plugin.py at singleton scope.

from __future__ import annotations

import threading
import uuid
import weakref
from collections import defaultdict
from typing import Any

from ..domain.entities.bridge_events import BridgeEvent, BridgeEventType
from ..domain.ports.event_bus import EventBus, EventHandler, SubscriptionToken


def _make_weak(handler: EventHandler) -> Any:
	try:
		return weakref.WeakMethod(handler)
	except TypeError:
		return weakref.ref(handler)


def _resolve(wh: Any) -> EventHandler | None:
	return wh()  # type: ignore[no-any-return]


class SimpleEventBus(EventBus):
	"""One dict mapping token → _Entry, plus a per-type index for fast emit.
	All data-structure access is guarded by ``_lock`` because emit() can
	run on the server thread while subscribe()/unsubscribe() run on main.
	"""

	def __init__(self) -> None:
		self._lock = threading.Lock()
		self._entries: dict[SubscriptionToken, _Entry] = {}
		self._by_type: dict[BridgeEventType, list[SubscriptionToken]] = defaultdict(list)

	def subscribe(self, event_type: BridgeEventType, handler: EventHandler) -> SubscriptionToken:
		token = uuid.uuid4().hex
		entry = _Entry(event_type, _make_weak(handler))
		with self._lock:
			self._entries[token] = entry
			self._by_type[event_type].append(token)
		return token

	def unsubscribe(self, token: SubscriptionToken) -> None:
		with self._lock:
			entry = self._entries.pop(token, None)
			if entry is None:
				return
			tokens = self._by_type.get(entry.event_type)
			if tokens is not None:
				try:
					tokens.remove(token)
				except ValueError:
					pass

	def emit(self, event: BridgeEvent) -> None:
		with self._lock:
			tokens = list(self._by_type.get(event.type, ()))
		# Call handlers outside the lock so a handler that emits back (or
		# takes a long time) doesn't block other threads from subscribing.
		dead: list[SubscriptionToken] = []
		for token in tokens:
			with self._lock:
				entry = self._entries.get(token)
			if entry is None:
				dead.append(token)
				continue
			fn = _resolve(entry.weak_handler)
			if fn is None:
				dead.append(token)
				with self._lock:
					self._entries.pop(token, None)
				continue
			try:
				fn(event)
			except Exception:
				pass
		if dead:
			with self._lock:
				by_type = self._by_type.get(event.type)
				if by_type is not None:
					for t in dead:
						try:
							by_type.remove(t)
						except ValueError:
							pass


#: Internal record for one subscription.
class _Entry:
	__slots__ = ("event_type", "weak_handler")

	def __init__(self, event_type: BridgeEventType, weak_handler: Any) -> None:
		self.event_type = event_type
		self.weak_handler = weak_handler
