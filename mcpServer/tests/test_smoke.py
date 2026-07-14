# Smoke tests for the server skeleton. Real tool/fake-bridge tests land in
# milestone 4 (session D). Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2+.

from __future__ import annotations

import pytest

import nvda_mcp
from nvda_mcp_wire import PROTOCOL_VERSION, Command


def test_version_exposed() -> None:
	assert nvda_mcp.__version__


def test_main_is_a_placeholder_until_milestone_4() -> None:
	with pytest.raises(SystemExit):
		nvda_mcp.main()


def test_server_can_import_shared_wire_contract() -> None:
	# The whole point of the shared package: the server sees the same contract
	# the bridge ships. A trivial touch here fails loudly if the path dep breaks.
	assert PROTOCOL_VERSION == 1
	assert "hello" in Command.ALL
