# Unit tests for wiring.py -- the composition root.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# Proves build_session assembles a working stack from pure parts: a real
# JsonLinesChannel over the given transport, a real command registry (whose
# hello handler holds the factory), and a real session transcript on disk. We
# drive one hello through it, so the assertions ride on observable behaviour --
# a JSON-framed reply on the transport and a log file under tmp_path -- rather
# than reaching into the Session's privates.

from __future__ import annotations

from pathlib import Path

from fakes.adapter_factory import FakeAdapterFactory
from fakes.transport import FakeTransport

from nvdaMcpBridge import protocol as p
from nvdaMcpBridge.domain.controllers.session import Session
from nvdaMcpBridge.wiring import build_session


def test_build_session_composes_a_working_stack(tmp_path: Path) -> None:
	hello = p.encode_message(
		p.Request(id=1, cmd="hello", params={"mode": "silent", "protocolVersion": p.PROTOCOL_VERSION})
	)
	transport = FakeTransport([hello], on_empty="closed")
	factory = FakeAdapterFactory()

	session = build_session(transport, factory, tmp_path, "2026.1.0")
	assert isinstance(session, Session)
	session.run()

	# The registry the wiring built dispatched hello through to the factory.
	assert factory.built_mode is p.CaptureMode.SILENT
	# The reply came back JSON-framed on the transport, decodable to a HelloResult.
	responses = transport.responses()
	assert responses[0]["result"]["mode"] == "silent"
	assert responses[0]["result"]["nvdaVersion"] == "2026.1.0"
	assert bytes(transport.outbox).endswith(b"\n")
	# A real session transcript landed under logs_dir.
	assert len(list(tmp_path.glob("session-*.log"))) == 1
