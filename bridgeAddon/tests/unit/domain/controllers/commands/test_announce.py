# Unit tests for domain/controllers/commands/announce.py.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.

from __future__ import annotations

import pytest
from fakes.announcer import FakeAnnouncer
from fakes.clock import FakeClock
from support.context import make_context, request

from nvdaMcpBridge import protocol as p
from nvdaMcpBridge.domain.controllers.commands.announce import AnnounceHandler


def test_announce_speaks_the_text_and_acks(clock: FakeClock) -> None:
	announcer = FakeAnnouncer()
	ctx = make_context(clock, announcer=announcer)

	result = AnnounceHandler().execute(ctx, request("announce", text="pressing F7 now"))

	assert announcer.announced == ["pressing F7 now"]
	assert isinstance(result, p.AckResult)
	assert result.ok is True


def test_announce_rejects_missing_text(clock: FakeClock) -> None:
	ctx = make_context(clock, announcer=FakeAnnouncer())
	with pytest.raises(p.ValidationError):
		AnnounceHandler().execute(ctx, request("announce"))
