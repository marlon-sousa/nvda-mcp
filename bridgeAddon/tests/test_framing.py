# Tests for JSON-lines framing. Copyright (C) 2026 Marlon Brandao de Sousa.
# GPL-2. See COPYING.txt.

from __future__ import annotations

import pytest
from fakes import EOF_EVENT, TIMEOUT_EVENT, FakeTransport

from nvdaMcpBridge import protocol as p
from nvdaMcpBridge.domain.framing import TIMEOUT, Connection, ConnectionClosed


def test_reads_a_whole_message() -> None:
	transport = FakeTransport([p.encode_message({"id": 1, "cmd": "ping"})])
	conn = Connection(transport)
	assert conn.read_message() == {"id": 1, "cmd": "ping"}


def test_reassembles_a_message_split_across_chunks() -> None:
	line = p.encode_message({"id": 7, "cmd": "ping"})
	# A partial chunk yields TIMEOUT (nothing complete yet), then the rest lands.
	transport = FakeTransport([line[:4], line[4:]])
	conn = Connection(transport)
	assert conn.read_message() == {"id": 7, "cmd": "ping"}


def test_two_messages_in_one_chunk_are_delivered_separately() -> None:
	blob = p.encode_message({"id": 1, "cmd": "ping"}) + p.encode_message({"id": 2, "cmd": "bye"})
	transport = FakeTransport([blob])
	conn = Connection(transport)
	assert conn.read_message() == {"id": 1, "cmd": "ping"}
	# Second message comes from the buffer without touching the transport again.
	assert conn.read_message() == {"id": 2, "cmd": "bye"}


def test_timeout_is_reported_as_the_sentinel() -> None:
	transport = FakeTransport([TIMEOUT_EVENT])
	conn = Connection(transport)
	assert conn.read_message() is TIMEOUT


def test_eof_raises_connection_closed() -> None:
	transport = FakeTransport([EOF_EVENT])
	conn = Connection(transport)
	with pytest.raises(ConnectionClosed):
		conn.read_message()


def test_malformed_line_raises_validation_error() -> None:
	transport = FakeTransport([b"not json\n"])
	conn = Connection(transport)
	with pytest.raises(p.ValidationError):
		conn.read_message()


def test_write_encodes_dataclass_as_one_line() -> None:
	transport = FakeTransport([])
	conn = Connection(transport)
	conn.write(p.Response(id=3, result=p.AckResult()))
	assert transport.responses() == [{"id": 3, "result": {"ok": True}, "error": None}]
