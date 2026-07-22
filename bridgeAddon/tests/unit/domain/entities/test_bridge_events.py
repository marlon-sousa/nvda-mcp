# nvdaMcpBridge tests -- unit tests for the BridgeEvent DTO and BridgeEventType enum.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.

from __future__ import annotations

import pytest

from nvdaMcpBridge.domain.entities.bridge_events import BridgeEvent, BridgeEventType


def test_event_type_members() -> None:
	assert BridgeEventType.SERVER_STATUS == "server-status"
	assert len(BridgeEventType) == 1


def test_bridge_event_is_frozen() -> None:
	evt = BridgeEvent(type=BridgeEventType.SERVER_STATUS, payload="test")
	with pytest.raises(Exception):
		evt.type = BridgeEventType.SERVER_STATUS  # type: ignore[misc]


def test_bridge_event_is_hashable() -> None:
	evt = BridgeEvent(type=BridgeEventType.SERVER_STATUS, payload=None)
	assert hash(evt) is not None


def test_bridge_event_payload_defaults_to_none() -> None:
	evt = BridgeEvent(type=BridgeEventType.SERVER_STATUS)
	assert evt.payload is None


def test_bridge_event_equality() -> None:
	a = BridgeEvent(type=BridgeEventType.SERVER_STATUS, payload="x")
	b = BridgeEvent(type=BridgeEventType.SERVER_STATUS, payload="x")
	c = BridgeEvent(type=BridgeEventType.SERVER_STATUS, payload="y")
	assert a == b
	assert a != c
