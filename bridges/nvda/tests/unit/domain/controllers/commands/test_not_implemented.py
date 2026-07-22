# Unit tests for domain/controllers/commands/not_implemented.py.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.

from __future__ import annotations

import pytest
from fakes.clock import FakeClock
from support.context import make_context, request

from nvdaMcpBridge.domain.controllers.commands.command_handler import CommandError
from nvdaMcpBridge.domain.controllers.commands.not_implemented import NotImplementedHandler


def test_not_implemented_raises_a_clean_command_error(clock: FakeClock) -> None:
	with pytest.raises(CommandError) as exc:
		NotImplementedHandler().execute(make_context(clock), request("getState"))
	assert "getState" in str(exc.value)
	assert "not implemented" in str(exc.value)
