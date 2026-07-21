# nvdaMcpBridge -- the NVDA global plugin (the NVDA edge).
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# This file imports NVDA and is therefore in pyright's ``ignore`` list (see
# pyproject.toml): it is the thin edge, kept deliberately small, with all real
# logic living in the strict-checked ``domain/`` and the adapters. It is
# validated by the live-NVDA checklist (spec 0007, 9c), not by the type checker.
#
# ROLE: the composition root's NVDA end. On load it builds the connection stack
# (session C: NvdaAdapterFactory + TcpListener + BridgeServer) and starts it; on
# unload, or on the panic gesture, it stops the server -- which tears down any
# active session and thereby restores the user's synth. The per-connection wiring
# itself lives in wiring.build_session; this file only chooses the real adapters
# and owns the NVDA lifecycle (init / terminate / script).

from __future__ import annotations

import os

import buildVersion
import globalPluginHandler
import globalVars
import ui
import wx
from logHandler import log
from scriptHandler import script

from . import protocol
from .adapters.bridge_server import BridgeServer
from .adapters.nvda_adapter_factory import NvdaAdapterFactory
from .adapters.nvda_announcer import NvdaAnnouncer
from .adapters.nvda_log_capture import NvdaLogCapture
from .adapters.nvda_session_signals import NvdaSessionSignals
from .adapters.tcp_listener import TcpListener
from .wiring import build_session


def _bridge_logs_dir() -> str:
	"""Where session transcripts and NVDA-log captures land: ``<configPath>/nvdaMcpBridge``.

	One directory, two file-prefix families (``session-*.log``,
	``nvda-log-*.log``) -- each stack's own pruning only ever touches its own.
	"""
	return os.path.join(globalVars.appArgs.configPath, "nvdaMcpBridge")


class GlobalPlugin(globalPluginHandler.GlobalPlugin):
	"""Entry point NVDA instantiates when the addon loads.

	Builds and starts the bridge server (loopback, ``DEFAULT_PORT``). One session
	at a time. The synth is never swapped -- silent mode just suppresses NVDA's
	speech at the speak() filter -- so ending a session (bye, panic gesture, or
	NVDA shutdown) simply unregisters that filter and speech resumes at once.
	"""

	# The default Input Gestures category for this plugin's scripts.
	scriptCategory = _("NVDA MCP Bridge")

	def __init__(self) -> None:
		super().__init__()
		factory = NvdaAdapterFactory()
		listener = TcpListener("127.0.0.1", protocol.DEFAULT_PORT)
		logs_dir = _bridge_logs_dir()
		nvda_version = buildVersion.version
		signals = NvdaSessionSignals()
		announcer = NvdaAnnouncer()
		log_capture = NvdaLogCapture(logs_dir)

		def make_session(transport):
			return build_session(transport, factory, logs_dir, nvda_version, signals, announcer, log_capture)

		self._server = BridgeServer(listener, make_session)
		try:
			self._server.start()
			log.info(f"nvdaMcpBridge: listening on {self._server.status.endpoint}")
		except Exception:
			# A bind failure (e.g. the port is already in use by another NVDA)
			# must not break addon load: log it and stay stopped. The server is
			# still safe to stop() later; the 9.1 control dialog will surface this.
			log.error("nvdaMcpBridge: could not start the bridge server", exc_info=True)

	@script(
		# Translators: Input help message for the NVDA MCP bridge panic command.
		description=_("Stop the NVDA MCP bridge: end any active session and resume NVDA's speech"),
		gesture="kb:NVDA+control+shift+b",
	)
	def script_panic(self, gesture) -> None:
		# stop() joins the server thread, whose teardown unregisters the speech
		# filter -- so speech is already flowing again by the time this returns.
		self._server.stop()
		# Queue the confirmation after the session-end beep (also queued during
		# teardown), so it is spoken through the now-unsuppressed synth.
		# Translators: Announced after the panic gesture stops the bridge.
		wx.CallAfter(ui.message, _("NVDA MCP bridge stopped"))

	def terminate(self) -> None:
		self._server.stop()
		super().terminate()
