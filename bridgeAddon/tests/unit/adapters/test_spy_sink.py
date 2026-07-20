# Unit tests for adapters/spy_sink.py.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# spy_sink is the one pure, strict-checked file of the otherwise NVDA-facing
# capture path, so it is the only part unit-testable headlessly. The module holds
# a single global sink (one session at a time), so each test clears it first.

from __future__ import annotations

from typing import Sequence

import pytest

from nvdaMcpBridge.adapters import spy_sink


@pytest.fixture(autouse=True)
def reset_sink() -> None:
	spy_sink.clear_sink()


def test_notify_delivers_chunks_to_the_registered_sink() -> None:
	seen: list[Sequence[str]] = []
	spy_sink.set_sink(seen.append)
	spy_sink.notify(["Elements", " list"])
	assert seen == [["Elements", " list"]]


def test_notify_without_a_sink_is_a_no_op() -> None:
	spy_sink.notify(["nobody is listening"])  # must not raise


def test_clear_sink_stops_delivery() -> None:
	seen: list[Sequence[str]] = []
	spy_sink.set_sink(seen.append)
	spy_sink.clear_sink()
	spy_sink.notify(["dropped"])
	assert seen == []


def test_set_sink_replaces_the_previous_sink() -> None:
	first: list[Sequence[str]] = []
	second: list[Sequence[str]] = []
	spy_sink.set_sink(first.append)
	spy_sink.set_sink(second.append)
	spy_sink.notify(["only the second"])
	assert first == []
	assert second == [["only the second"]]


def test_clear_sink_is_idempotent() -> None:
	spy_sink.clear_sink()
	spy_sink.clear_sink()  # must not raise


def test_spy_synth_name_is_the_wire_driver_name() -> None:
	assert spy_sink.SPY_SYNTH_NAME == "nvdaMcpSpy"
