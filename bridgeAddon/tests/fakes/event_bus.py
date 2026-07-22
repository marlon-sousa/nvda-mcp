# nvdaMcpBridge test doubles -- FakeEventBus: the EventBus port in memory.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# ROLE: fake (subclasses EventBus). Records emitted events and lets tests
#       inject events to simulate external triggers. One handler list per
#       event type.

from __future__ import annotations

from collections import defaultdict

from nvdaMcpBridge.domain.entities.bridge_events import BridgeEvent, BridgeEventType
from nvdaMcpBridge.domain.ports.event_bus import EventBus, EventHandler, SubscriptionToken


class FakeEventBus(EventBus):
	"""In-memory event bus for tests. Records every emit in ``events``."""

	def __init__(self) -> None:
		self._next_token = 0
		self._handlers: dict[BridgeEventType, list[EventHandler]] = defaultdict(list)
		self.events: list[BridgeEvent] = []

	def subscribe(self, event_type: BridgeEventType, handler: EventHandler) -> SubscriptionToken:
		self._next_token += 1
		token = str(self._next_token)
		self._handlers[event_type].append(handler)
		return token

	def unsubscribe(self, token: SubscriptionToken) -> None:
		# Token-based unsubscribe is not needed for current tests; no-op.
		pass

	def emit(self, event: BridgeEvent) -> None:
		self.events.append(event)
		for handler in tuple(self._handlers.get(event.type, ())):
			handler(event)
