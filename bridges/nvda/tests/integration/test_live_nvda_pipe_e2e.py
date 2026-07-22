# Live-NVDA end-to-end scenario: drive the REAL bridge over a named pipe.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# EXPERIMENTAL, spec 0010's ad-hoc live check -- not a merge gate for entry
# 9.1a. Mirrors test_live_nvda_e2e.py exactly, dialling `DEFAULT_PIPE_NAME`
# with named_pipe_transport.dial() instead of a TCP socket, to prove
# NamedPipeListener against a real NVDA before 9.1b makes the pipe the
# plugin's default for real. Requires plugin.py's uncommitted swap to
# `NamedPipeListener(protocol.DEFAULT_PIPE_NAME)` (see plugin.py) -- with the
# stock TCP-listening addon installed, every test here SKIPS at the dial,
# same as test_live_nvda_e2e.py does with nothing listening.
#
# Run it locally with NVDA up, the pipe-listening build of the addon
# installed, and plugins reloaded (NVDA+control+F3):
#
#     uv run --directory bridges/nvda --with pytest pytest tests/integration/test_live_nvda_pipe_e2e.py -v

from __future__ import annotations

import time
from typing import Any

import pytest

from nvdaMcpBridge import protocol as p
from nvdaMcpBridge.adapters import named_pipe_transport
from nvdaMcpBridge.adapters.json_lines_channel import JsonLinesChannel
from nvdaMcpBridge.domain.controllers.commands.registry import NVDA_CAPABILITIES
from nvdaMcpBridge.domain.ports.message_channel import Timeout

#: Same choice as test_live_nvda_e2e.py: speaks in essentially any focus
#: context, so the capture assertion does not depend on a particular window.
SPEAKING_GESTURE = "NVDA+t"


@pytest.fixture(scope="module", autouse=True)
def require_live_bridge() -> None:
	try:
		named_pipe_transport.dial(p.DEFAULT_PIPE_NAME, timeout=0.5).close()
	except (OSError, TimeoutError):
		pytest.skip(
			f"no bridge on pipe {p.DEFAULT_PIPE_NAME!r} -- start NVDA with a "
			"pipe-listening build of the nvdaMcpBridge addon installed"
		)


class Agent:
	"""The client end of one bridge session: send a command, read its reply."""

	def __init__(self, channel: JsonLinesChannel) -> None:
		self._channel = channel
		self._id = 0

	def call(self, cmd: str, *, reply_timeout: float = 10.0, **params: Any) -> dict[str, Any]:
		self._id += 1
		self._channel.write(p.Request(id=self._id, cmd=cmd, params=dict(params)))
		deadline = time.monotonic() + reply_timeout
		while time.monotonic() < deadline:
			message = self._channel.read_message()
			if isinstance(message, Timeout):
				continue
			if message.get("error") is not None:
				raise AssertionError(f"{cmd} failed: {message['error']}")
			return message
		raise AssertionError(f"no reply to {cmd} within {reply_timeout}s")

	def result(self, cmd: str, **params: Any) -> dict[str, Any]:
		return self.call(cmd, **params)["result"]

	def close(self) -> None:
		self._channel.close()


def _dial() -> Agent:
	try:
		transport = named_pipe_transport.dial(p.DEFAULT_PIPE_NAME, timeout=1.0)
	except (OSError, TimeoutError):
		pytest.skip(
			f"no bridge on pipe {p.DEFAULT_PIPE_NAME!r} -- start NVDA with a "
			"pipe-listening build of the nvdaMcpBridge addon installed"
		)
	return Agent(JsonLinesChannel(transport))


def _hello(agent: Agent, mode: str) -> dict[str, Any]:
	return agent.result("hello", mode=mode, protocolVersion=p.PROTOCOL_VERSION)


def test_hello_reports_real_nvda_and_served_capabilities() -> None:
	agent = _dial()
	try:
		hello = _hello(agent, "silent")
		assert hello["reader"]["name"] == "nvda"
		assert hello["reader"]["version"], "reader.version should match About NVDA"
		assert hello["capabilities"] == [c.value for c in NVDA_CAPABILITIES]
		assert hello["mode"] == "silent"
		assert hello["synth"], "hello should report NVDA's real synth"
		agent.result("bye")
	finally:
		agent.close()


def test_silent_session_captures_a_gesture_and_finishes() -> None:
	agent = _dial()
	try:
		_hello(agent, "silent")
		start = agent.result("getNextSpeechIndex")["index"]
		assert agent.result("pressGesture", gestures=[SPEAKING_GESTURE]) == {"ok": True}
		assert agent.result("waitForSpeechToFinish", timeout=3.0)["finished"] is True
		speech = agent.result("getSpeech", sinceIndex=start)
		assert speech["text"].strip(), "the gesture should have been captured as speech"
		assert speech["toIndex"] > speech["fromIndex"]
		agent.result("bye")
	finally:
		agent.close()


def test_two_sequential_sessions_on_one_server() -> None:
	synths: list[str] = []
	for _ in range(2):
		agent = _dial()
		try:
			synths.append(_hello(agent, "silent")["synth"])
			agent.result("bye")
		finally:
			agent.close()
	assert synths[0] == synths[1]
	assert synths[0]  # a real synth name, stable across sessions
