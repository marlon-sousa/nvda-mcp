# nvdaMcpBridge tests -- unit tests for the ConnectionMode entity.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.

from __future__ import annotations

from nvdaMcpBridge.domain.entities.connection_mode import DEFAULT, ConnectionMode


class TestConnectionMode:
	"""The ConnectionMode enum: three members, DEFAULT is NAMED_PIPE, string values match."""

	def test_members(self) -> None:
		members = list(ConnectionMode)
		assert len(members) == 3
		assert ConnectionMode.NAMED_PIPE in members
		assert ConnectionMode.LOOPBACK_TCP in members
		assert ConnectionMode.REMOTE_TCP in members

	def test_default_is_named_pipe(self) -> None:
		assert DEFAULT is ConnectionMode.NAMED_PIPE

	def test_string_values(self) -> None:
		assert ConnectionMode.NAMED_PIPE.value == "namedPipe"
		assert ConnectionMode.LOOPBACK_TCP.value == "loopbackTcp"
		assert ConnectionMode.REMOTE_TCP.value == "remoteTcp"

	def test_str_enum_members_are_strings(self) -> None:
		# StrEnum members *are* str, so they compare equal to their wire value.
		assert isinstance(ConnectionMode.NAMED_PIPE, str)
		assert ConnectionMode.NAMED_PIPE == "namedPipe"

	def test_from_string_round_trips(self) -> None:
		assert ConnectionMode("namedPipe") is ConnectionMode.NAMED_PIPE
		assert ConnectionMode("loopbackTcp") is ConnectionMode.LOOPBACK_TCP
		assert ConnectionMode("remoteTcp") is ConnectionMode.REMOTE_TCP
