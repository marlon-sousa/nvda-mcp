# nvdaMcpBridge -- the composition root.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# ROLE: the ONE place that knows both sides of the hexagon. It picks concrete
#       adapters, stacks them, and hands the resulting PORTS to the controller.
#       If you want to know "who connects what", the answer is: right here.
# CALLED BY: plugin.py (the NVDA edge), once per accepted connection (session C).
#
# It stays PURE -- domain + pure adapters only, no NVDA -- so it is fully
# type-checked and testable. The NVDA-specific choices (which AdapterFactory,
# which socket) are made in plugin.py and injected, which keeps the file that
# knows both sides free of the untestable edge.

from __future__ import annotations

from typing import TYPE_CHECKING

from .adapters.json_lines_channel import JsonLinesChannel
from .domain.controllers.session import Session, SessionConfig, TeardownReason

if TYPE_CHECKING:
	from .adapters.ports.transport import Transport
	from .domain.ports.adapter_factory import AdapterFactory
	from .domain.ports.clock import Clock
	from .domain.ports.message_channel import MessageChannel
	from .domain.ports.transcript import Transcript


def serve(
	channel: MessageChannel,
	*,
	clock: Clock,
	transcript: Transcript,
	factory: AdapterFactory,
	nvda_version: str,
	config: SessionConfig | None = None,
) -> TeardownReason:
	"""Run one session over an already-built message channel, to completion.

	Every collaborator here is a port, which is exactly the point: the
	controller is handed its seams and orchestrates the rest.
	"""
	session = Session(
		channel,
		clock,
		transcript,
		factory,
		nvda_version=nvda_version,
		config=config,
	)
	return session.run()


def serve_transport(
	transport: Transport,
	*,
	clock: Clock,
	transcript: Transcript,
	factory: AdapterFactory,
	nvda_version: str,
	config: SessionConfig | None = None,
) -> TeardownReason:
	"""Compose the wire stack over a byte transport, then :func:`serve` it.

	This is the composition step for a real connection: JSON-lines framing on
	top of whatever byte pipe the edge accepted. Session C's plugin calls this
	with a SocketTransport.
	"""
	return serve(
		JsonLinesChannel(transport),
		clock=clock,
		transcript=transcript,
		factory=factory,
		nvda_version=nvda_version,
		config=config,
	)
