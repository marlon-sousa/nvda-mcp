# Unit tests for domain/controllers/commands/press_gesture.py.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.

from __future__ import annotations

import pytest
from fakes.adapter_factory import FakeAdapterFactory
from fakes.clock import FakeClock
from fakes.transcript import FakeTranscript
from support.context import adapters_from, make_context, request

from nvdaMcpBridge import protocol as p
from nvdaMcpBridge.domain.controllers.commands.press_gesture import PressGestureHandler
from nvdaMcpBridge.domain.ports.gesture_sender import GestureError


def _gestures(transcript: FakeTranscript) -> list[tuple[object, ...]]:
	return [event for event in transcript.events if event[0] == "gesture"]


def test_presses_in_order_and_logs_each(clock: FakeClock) -> None:
	factory = FakeAdapterFactory()
	transcript = FakeTranscript()
	ctx = make_context(clock, transcript=transcript, adapters=adapters_from(factory))
	result = PressGestureHandler().execute(ctx, request("pressGesture", gestures=["a", "b"]))
	assert isinstance(result, p.AckResult)
	assert factory.gesture_sender.pressed == ["a", "b"]
	assert _gestures(transcript) == [("gesture", "a"), ("gesture", "b")]


def test_gesture_error_aborts_the_remainder(clock: FakeClock) -> None:
	factory = FakeAdapterFactory(reject=["bad"])
	transcript = FakeTranscript()
	ctx = make_context(clock, transcript=transcript, adapters=adapters_from(factory))
	with pytest.raises(GestureError):
		PressGestureHandler().execute(ctx, request("pressGesture", gestures=["a", "bad", "c"]))
	# "a" pressed, "bad" rejected, "c" never reached; "a" and "bad" both logged
	# (the transcript entry precedes the press).
	assert factory.gesture_sender.pressed == ["a"]
	assert _gestures(transcript) == [("gesture", "a"), ("gesture", "bad")]
