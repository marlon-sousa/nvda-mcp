# Tests for the JsonLinesChannel adapter: framing + encode/decode over a byte
# transport. Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# This is the ONLY place bytes appear in the tests. The Session's own tests
# script whole messages against a FakeChannel, so they stay about the session.

from __future__ import annotations

import pytest
from fakes import CLOSED_EVENT, TIMEOUT_EVENT, FakeTransport

from nvdaMcpBridge import protocol as p
from nvdaMcpBridge.adapters.json_lines_channel import JsonLinesChannel
from nvdaMcpBridge.domain.ports.message_channel import TIMEOUT, ChannelClosed


def test_reads_a_whole_message() -> None:
	channel = JsonLinesChannel(FakeTransport([p.encode_message({"id": 1, "cmd": "ping"})]))
	assert channel.read_message() == {"id": 1, "cmd": "ping"}


def test_reassembles_a_message_split_across_chunks() -> None:
	line = p.encode_message({"id": 7, "cmd": "ping"})
	channel = JsonLinesChannel(FakeTransport([line[:4], line[4:]]))
	assert channel.read_message() == {"id": 7, "cmd": "ping"}


def test_two_messages_in_one_chunk_are_delivered_separately() -> None:
	blob = p.encode_message({"id": 1, "cmd": "ping"}) + p.encode_message({"id": 2, "cmd": "bye"})
	channel = JsonLinesChannel(FakeTransport([blob]))
	assert channel.read_message() == {"id": 1, "cmd": "ping"}
	# Second message comes from the buffer without touching the transport again.
	assert channel.read_message() == {"id": 2, "cmd": "bye"}


def test_timeout_is_reported_as_the_sentinel() -> None:
	channel = JsonLinesChannel(FakeTransport([TIMEOUT_EVENT]))
	assert channel.read_message() is TIMEOUT


def test_eof_raises_channel_closed() -> None:
	channel = JsonLinesChannel(FakeTransport([CLOSED_EVENT]))
	with pytest.raises(ChannelClosed):
		channel.read_message()


def test_unreadable_line_raises_validation_error() -> None:
	# The Session turns this into an error response rather than dying; see
	# test_session.test_unreadable_message_is_reported_and_the_loop_continues.
	channel = JsonLinesChannel(FakeTransport([b"not json\n"]))
	with pytest.raises(p.ValidationError):
		channel.read_message()


def test_write_encodes_dataclass_as_one_line() -> None:
	transport = FakeTransport([])
	JsonLinesChannel(transport).write(p.Response(id=3, result=p.AckResult()))
	assert transport.responses() == [{"id": 3, "result": {"ok": True}, "error": None}]


def test_close_closes_the_transport() -> None:
	transport = FakeTransport([])
	JsonLinesChannel(transport).close()
	assert transport.closed is True
