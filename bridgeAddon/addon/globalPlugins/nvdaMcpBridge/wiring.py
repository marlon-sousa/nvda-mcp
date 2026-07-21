# nvdaMcpBridge -- wiring.py: the composition root.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# ROLE: the composition root -- read top to bottom, it IS the answer to "who
# connects what". It stacks the pure adapters and hands the Session its ports;
# it stays PURE (no NVDA import) so pyright type-checks the whole graph.
# BUILT BY: session C's accept loop, once per accepted connection.
#
# The two NVDA-facing pieces are PARAMETERS, not built here, precisely because
# they are session C's edge: `transport` (a real SocketTransport there; a
# LoopbackTransport in tests) and `factory` (the real AdapterFactory there; a
# fake in tests). Everything else -- the transcript stack, the JSON-lines
# channel, the clock, the command registry -- is assembled from pure parts.

from __future__ import annotations

from typing import TYPE_CHECKING

from .adapters.file_transcript import create_session_log
from .adapters.json_lines_channel import JsonLinesChannel
from .adapters.real_clock import RealClock
from .domain.controllers.commands.registry import build_command_registry
from .domain.controllers.session import Session, SessionConfig

if TYPE_CHECKING:
	import os

	from .adapters.ports.transport import Transport
	from .domain.ports.adapter_factory import AdapterFactory
	from .domain.ports.announcer import Announcer
	from .domain.ports.log_capture import LogCapture
	from .domain.ports.session_signals import SessionSignals


def build_session(
	transport: Transport,
	factory: AdapterFactory,
	logs_dir: str | os.PathLike[str],
	nvda_version: str,
	signals: SessionSignals,
	announcer: Announcer,
	log_capture: LogCapture,
	*,
	heartbeat_timeout: float = 30.0,
	inactivity_timeout: float = 120.0,
) -> Session:
	"""Assemble a Session for one connection over ``transport``.

	Opens a fresh session transcript under ``logs_dir``, wraps ``transport`` in
	the JSON-lines channel, builds the command registry (whose hello handler
	holds ``factory``), and hands the Session its ports -- including the session
	``signals`` (start/end beeps), the ``announcer`` (the bridge's line to the
	real synth, for the hello synth name and the announce hint channel), and
	``log_capture`` (the NVDA-log tee the hello handler starts, spec 0009).
	``log_capture`` is NVDA-facing like ``signals``/``announcer``, so it is a
	parameter built at the edge (plugin.py), not constructed here -- wiring.py
	stays pure.
	"""
	transcript = create_session_log(logs_dir)
	channel = JsonLinesChannel(transport)
	clock = RealClock()
	registry = build_command_registry(factory, nvda_version)
	config = SessionConfig(
		nvda_version=nvda_version,
		heartbeat_timeout=heartbeat_timeout,
		inactivity_timeout=inactivity_timeout,
	)
	return Session(channel, transcript, clock, config, registry, signals, announcer, log_capture)
