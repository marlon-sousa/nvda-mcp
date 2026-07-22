# nvdaMcpBridge domain -- TeardownReason: why a session ended.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# ROLE: a domain-only enum (plain Enum, per AGENTS.md -- it never crosses the
# wire, so it is not a StrEnum in protocol.py).
# USED BY: the Session controller (sets it on every exit path), the
# SessionContext's close() capability (a command asks to end the session with a
# reason), and the Transcript (the value is the human string on SESSION CLOSE).
#
# It lives in its own file so both session.py and commands/session_context.py can
# import it without a cycle (the context's close() takes a reason; the Session
# owns the teardown that consumes it).

from __future__ import annotations

import enum


class TeardownReason(enum.Enum):
	"""Why a session ended; the value is the transcript's SESSION CLOSE string."""

	CLIENT_BYE = "client-bye"
	CHANNEL_CLOSED = "channel-closed"
	HEARTBEAT_TIMEOUT = "heartbeat-timeout"
	INACTIVITY_TIMEOUT = "inactivity-timeout"
	HANDSHAKE_FAILED = "handshake-failed"
	EXTERNAL = "external"
