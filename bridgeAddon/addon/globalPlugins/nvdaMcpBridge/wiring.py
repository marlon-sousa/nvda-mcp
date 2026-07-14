# nvdaMcpBridge -- composition root.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# This is where ports meet adapters. It stays PURE (imports only the domain), so
# it is fully type-checked and unit-testable: the NVDA-specific choices -- which
# concrete AdapterFactory, which Transport, how the socket is accepted -- are
# made in ``plugin.py`` (the ignored edge, session C) and injected here. That
# keeps the one place that "knows both sides" free of NVDA.

from __future__ import annotations

from typing import TYPE_CHECKING

from .domain.framing import Connection
from .domain.session import Session, SessionConfig, TeardownReason

if TYPE_CHECKING:
	from .domain.ports import AdapterFactory, Clock, Transcript, Transport


def serve(
	transport: Transport,
	*,
	clock: Clock,
	transcript: Transcript,
	factory: AdapterFactory,
	nvda_version: str,
	config: SessionConfig | None = None,
) -> TeardownReason:
	"""Run a single session over ``transport`` to completion.

	Frames the transport, constructs a :class:`~.domain.session.Session` from the
	injected ports, and runs it. Session C's accept loop calls this once per
	accepted connection with NVDA-backed adapters; tests call it with fakes.
	"""
	session = Session(
		Connection(transport),
		clock,
		transcript,
		factory,
		nvda_version=nvda_version,
		config=config,
	)
	return session.run()
