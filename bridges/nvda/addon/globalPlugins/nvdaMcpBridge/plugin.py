# nvdaMcpBridge -- the NVDA global plugin (the NVDA edge).
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# This file imports NVDA and is therefore in pyright's ``ignore`` list (see
# pyproject.toml): it is the thin edge, kept deliberately small, with all real
# logic living in the strict-checked ``domain/`` and the adapters. It is
# validated by the live-NVDA checklist (spec 0007, 9c), not by the type checker.
#
# ROLE: the composition root's NVDA end. On load it reads persisted config,
# builds the matching Listener (named pipe by default; spec 0010 / 0011) and
# starts the bridge if auto-start is enabled. A control dialog (spec 0011,
# entry 9.1b PR C) will add a Tools menu item later.
# On unload, or on the panic gesture, it stops the server -- which tears down
# any active session and thereby restores the user's synth.
#
# The per-connection wiring itself lives in wiring.build_session; this file
# only chooses the real adapters and owns the NVDA lifecycle (init / terminate
# / script).

from __future__ import annotations

import os

import buildVersion
import globalPluginHandler
import globalVars
import gui
import ui
import wx
from logHandler import log
from scriptHandler import script

from .adapters.bridge_server import BridgeServer
from .adapters.build_listener import build_listener
from .adapters.ini_bridge_config import IniBridgeConfig
from .adapters.nvda_adapter_factory import NvdaAdapterFactory
from .adapters.nvda_announcer import NvdaAnnouncer
from .adapters.nvda_log import NvdaLog
from .adapters.nvda_log_capture import NvdaLogCapture
from .adapters.nvda_session_signals import NvdaSessionSignals
from .adapters.simple_event_bus import SimpleEventBus
from .adapters.text_config_file import TextConfigFile
from .domain.entities.connection_mode import ConnectionMode
from .views.bridge_dialog import BridgeDialog
from .wiring import build_session


def _bridge_logs_dir() -> str:
	"""Where session transcripts and NVDA-log captures land: ``<configPath>/nvdaMcpBridge``.

	One directory, two file-prefix families (``session-*.log``,
	``nvda-log-*.log``) -- each stack's own pruning only ever touches its own.
	The ``config/`` subdirectory (config.ini) lives here too (spec 0011).
	"""
	return os.path.join(globalVars.appArgs.configPath, "nvdaMcpBridge")


class GlobalPlugin(globalPluginHandler.GlobalPlugin):
	"""Entry point NVDA instantiates when the addon loads.

	Builds and starts the bridge server on the persisted connection mode
	(named pipe by default -- spec 0010 / 0011). One session at a time. The
	synth is never swapped -- silent mode just suppresses NVDA's speech at the
	speak() filter -- so ending a session (bye, panic gesture, or NVDA shutdown)
	simply unregisters that filter and speech resumes at once.
	"""

	# The default Input Gestures category for this plugin's scripts.
	scriptCategory = _("NVDA MCP Bridge")

	def __init__(self) -> None:
		super().__init__()

		# Config lives under the same parent directory as the logs (spec 0011).
		config_path = os.path.join(_bridge_logs_dir(), "config", "config.ini")
		self._log = NvdaLog()
		self._config = IniBridgeConfig(TextConfigFile(config_path), self._log)

		factory = NvdaAdapterFactory()
		listener = build_listener(self._config.get_connection_mode())
		logs_dir = _bridge_logs_dir()
		nvda_version = buildVersion.version
		signals = NvdaSessionSignals()
		announcer = NvdaAnnouncer()
		log_capture = NvdaLogCapture(logs_dir)
		self._event_bus = SimpleEventBus()

		def make_session(transport):
			return build_session(transport, factory, logs_dir, nvda_version, signals, announcer, log_capture)

		self._server = BridgeServer(listener, make_session, event_bus=self._event_bus)
		self._tools_menu_item: wx.MenuItem | None = None

		self._register_tools_menu_item()

		if self._config.get_auto_start():
			try:
				self._server.start()
				log.info(f"nvdaMcpBridge: listening on {self._server.status.endpoint}")
			except Exception:
				# A bind failure (e.g. another NVDA already holds the pipe name) must
				# not break addon load: log it and stay stopped. The control dialog
				# (PR C) lets the user retry.
				log.error("nvdaMcpBridge: could not start the bridge server", exc_info=True)

	# -- menu -----------------------------------------------------------------

	def _register_tools_menu_item(self) -> None:
		"""Add "NVDA MCP Bridge…" to NVDA's Tools menu.

		Guarded so reloads don't double-add. On systems where the NVDA GUI is
		not available (e.g. secure mode, no display) this is a no-op.
		"""
		if self._tools_menu_item is not None:
			return  # already registered (reload)
		try:
			tools_menu = gui.mainFrame.sysTrayIcon.toolsMenu
		except Exception:
			# No GUI available; the addon still works, just without the dialog.
			return
		# Translators: Menu item in NVDA's Tools menu to open the NVDA MCP Bridge dialog.
		self._tools_menu_item = tools_menu.Append(
			wx.ID_ANY, _("NVDA MCP &Bridge…"),
		)
		gui.mainFrame.sysTrayIcon.Bind(
			wx.EVT_MENU, lambda evt: self._show_bridge_dialog(), self._tools_menu_item
		)

	def _remove_tools_menu_item(self) -> None:
		"""Remove the Tools menu item; called from terminate()."""
		item = self._tools_menu_item
		if item is None:
			return
		try:
			tools_menu = gui.mainFrame.sysTrayIcon.toolsMenu
		except Exception:
			return
		tools_menu.Remove(item)
		self._tools_menu_item = None

	def _show_bridge_dialog(self) -> None:
		"""Open the bridge control dialog, injecting real dependencies."""
		# The dialog is modal (consistent with NVDA's own Tools-menu dialogs like
		# the Log Viewer).
		dlg = BridgeDialog(gui.mainFrame, self._server, self._config, self._event_bus)
		dlg.set_plugin(self)
		dlg.ShowModal()
		dlg.Destroy()

	# -- server lifecycle ------------------------------------------------------

	def start_server(self, mode: ConnectionMode) -> None:
		"""Persist *mode* and start the server with the matching listener.

		Called by BridgeDialog (PR C) when the user presses Start. Start is only
		enabled when the server is STOPPED, so there is nothing to tear down.
		"""
		self._config.set_connection_mode(mode)
		self._server.start(build_listener(mode))

	# -- panic gesture ---------------------------------------------------------

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
		self._remove_tools_menu_item()
		super().terminate()
