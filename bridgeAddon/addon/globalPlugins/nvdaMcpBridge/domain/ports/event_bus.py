# nvdaMcpBridge domain ports -- the EventBus port.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# ROLE: port (abc.ABC). A pub/sub channel the domain and adapters both use.
#       subscribe() returns an opaque token; the subscriber holds it and
#       passes it to unsubscribe(token) later — no need to keep the handler
#       reference around.
# IMPLEMENTED BY: adapters/simple_event_bus.py.
# USED BY: BridgeServer (emitter), BridgeDialog (subscriber).

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable

from ..entities.bridge_events import BridgeEvent, BridgeEventType

#: A handler registered for a specific event type.
EventHandler = Callable[[BridgeEvent], None]

#: Opaque token returned by subscribe(), consumed by unsubscribe().
SubscriptionToken = str


class EventBus(ABC):
	"""Pub/sub for bridge-domain events (server status, session lifecycle, …).

	Subscribers are called synchronously on the publishing thread. Handlers
	that touch a UI are responsible for marshalling (e.g. wx.CallAfter).
	"""

	@abstractmethod
	def subscribe(self, event_type: BridgeEventType, handler: EventHandler) -> SubscriptionToken:
		"""Register *handler* for *event_type*. Returns a token for later unsubscribe()."""

	@abstractmethod
	def unsubscribe(self, token: SubscriptionToken) -> None:
		"""Remove the subscription identified by *token*. Safe to call when already removed."""

	@abstractmethod
	def emit(self, event: BridgeEvent) -> None:
		"""Deliver *event* to every handler registered for its type."""
