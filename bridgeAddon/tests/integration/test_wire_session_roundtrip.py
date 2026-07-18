# Integration scenario: a whole session over the wire, headless.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# Named after the USE CASE, not a file: this drives a REAL session end to end
# through real framing and real dispatch, with no NVDA and no socket. It is the
# recipe lane 2's server<->bridge integration tests build on -- build_session
# over one end of a LoopbackTransport with a fake NVDA, run() on a thread, and
# the test plays the agent on the other end speaking raw protocol. Headless, so
# it runs in CI (unlike the live-NVDA scenarios, which stay milestone 6).

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any

from fakes.adapter_factory import FakeAdapterFactory
from fakes.loopback_transport import loopback_pair

from nvdaMcpBridge import protocol as p
from nvdaMcpBridge.adapters.json_lines_channel import JsonLinesChannel
from nvdaMcpBridge.domain.ports.message_channel import Timeout
from nvdaMcpBridge.wiring import build_session


def _request(id: int, cmd: str, **params: Any) -> p.Request:
	return p.Request(id=id, cmd=cmd, params=dict(params))


def _read_reply(agent: JsonLinesChannel, timeout: float = 5.0) -> dict[str, Any]:
	"""Read past the poll-timeouts until the bridge actually answers."""
	deadline = time.monotonic() + timeout
	while time.monotonic() < deadline:
		message = agent.read_message()
		if not isinstance(message, Timeout):
			return message
	raise AssertionError("no reply from the bridge within timeout")


def test_a_whole_session_over_the_wire(tmp_path: Path) -> None:
	bridge_end, agent_end = loopback_pair()
	factory = FakeAdapterFactory(speech={"NVDA+f7": ["Elements list dialog"]})
	session = build_session(bridge_end, factory, tmp_path, "2026.1.0")
	agent = JsonLinesChannel(agent_end)

	thread = threading.Thread(target=session.run, daemon=True)
	thread.start()
	try:
		# Handshake.
		agent.write(_request(1, "hello", mode="silent", protocolVersion=p.PROTOCOL_VERSION))
		hello = _read_reply(agent)
		assert hello["result"]["mode"] == "silent"
		assert hello["result"]["synth"] == "espeak"

		# Echo an awkward payload -- byte-exact through encode/frame/decode/validate.
		payload = {"u": "olá café \U0001f600", "nested": [1, 2, {"x": True}], "n": 3.5}
		agent.write(_request(2, "echo", payload=payload))
		assert _read_reply(agent)["result"]["payload"] == payload

		# Scripted gesture -> speech -> wait-to-finish -> read it back.
		agent.write(_request(3, "pressGesture", gestures=["NVDA+f7"]))
		assert _read_reply(agent)["result"] == {"ok": True}
		agent.write(_request(4, "waitForSpeechToFinish", timeout=1.0))
		assert _read_reply(agent)["result"]["finished"] is True
		agent.write(_request(5, "getSpeech", sinceIndex=0))
		assert "Elements list dialog" in _read_reply(agent)["result"]["text"]

		# Bye -> ack, then teardown restores the (fake) synth.
		agent.write(_request(6, "bye"))
		assert _read_reply(agent)["result"] == {"ok": True}
	finally:
		thread.join(timeout=5.0)

	assert not thread.is_alive()
	assert factory.synth_swapper.restores == 1
