# nvdaMcpBridge domain entities -- bridge event types and DTOs.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# ROLE: entity. A StrEnum of event types and a BridgeEvent DTO that the
#       EventBus port carries. Pure — no collaborators.

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class BridgeEventType(StrEnum):
	"""Well-known event types published on the bus."""

	SERVER_STATUS = "server-status"


@dataclass(frozen=True)
class BridgeEvent:
	"""An event on the bus: a type and an optional typed payload.

	The payload's shape depends on the event type; subscribers that registered
	for the type are expected to know it.
	"""

	type: BridgeEventType
	payload: Any = None
