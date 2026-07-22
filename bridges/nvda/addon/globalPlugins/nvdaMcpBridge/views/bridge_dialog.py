# nvdaMcpBridge views -- BridgeDialog: the bridge control UI (NVDA Tools menu).
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# ROLE: driving actor (view). A wx.Dialog that shows bridge status, lets the user
#       pick a connection mode, start/stop the server, and toggle auto-start.
#       Receives a BridgeConfig port and a BridgeServer via constructor injection.
# DEPENDS ON: wx, NVDA's gui, BridgeServer (adapter), BridgeConfig (domain port),
#             ConnectionMode (domain entity), and the Listener seam for build_listener.
# BUILT BY: plugin.py (_show_bridge_dialog -- the composition root for the view).
# USED BY: plugin.py's Tools menu item.
#
# This file imports wx and NVDA's GUI stack; it is in pyright's ``ignore`` list
# (see pyproject.toml). It is validated by the live-NVDA checklist.

from __future__ import annotations

from gui import guiHelper
import ui
import wx
from logHandler import log

from ..adapters.bridge_server import BridgeServer, ServerState
from ..domain.entities.bridge_events import BridgeEvent, BridgeEventType
from ..domain.entities.connection_mode import ConnectionMode
from ..domain.ports.bridge_config import BridgeConfig
from ..domain.ports.event_bus import EventBus


# -- combo helpers ---------------------------------------------------------------

# The combo has two entries in this exact order.
_COMBO_ENTRIES: tuple[ConnectionMode, ...] = (
	ConnectionMode.NAMED_PIPE,
	ConnectionMode.LOOPBACK_TCP,
)


def _mode_to_combo_index(mode: ConnectionMode) -> int:
	try:
		return _COMBO_ENTRIES.index(mode)
	except ValueError:
		return 0  # fallback: named pipe


def _combo_index_to_mode(index: int) -> ConnectionMode:
	if 0 <= index < len(_COMBO_ENTRIES):
		return _COMBO_ENTRIES[index]
	return ConnectionMode.NAMED_PIPE


# -- the dialog ----------------------------------------------------------------


class BridgeDialog(wx.Dialog):
	"""NVDA Tools → NVDA MCP Bridge… dialog.

	Shows the current bridge status, lets the user change the connection mode,
	start/stop the server, and toggle auto-start. Receives its dependencies
	(BridgeServer, BridgeConfig, EventBus) through constructor injection so
	plugin.py is the composition root.

	Subscribes to SERVER_STATUS events on the bus while open so the display
	stays live without polling.
	"""

	def __init__(
		self,
		parent: wx.Window,
		server: BridgeServer,
		config: BridgeConfig,
		event_bus: EventBus,
	) -> None:
		# Translators: Title of the NVDA MCP Bridge dialog.
		super().__init__(parent, title=_("NVDA MCP Bridge"))

		self._server = server
		self._config = config
		self._event_bus = event_bus

		# Hold a reference to the plugin for start_server().
		self._plugin: "GlobalPlugin | None" = None

		# Track previous state so we can announce transitions.
		self._last_state: ServerState | None = None

		self._build_ui()
		self._init_combo_from_config()
		self._refresh()

		# Subscribe to server-status events so the dialog updates immediately
		# when the server starts, stops, or a client connects/disconnects —
		# no polling. wx.CallAfter marshals to the main thread.
		self._sub_token = self._event_bus.subscribe(BridgeEventType.SERVER_STATUS, self._on_server_status)

		self.Bind(wx.EVT_CHAR_HOOK, self._on_char_hook)
		self.Bind(wx.EVT_CLOSE, self._on_close)

	# -- plugin back-reference --------------------------------------------------

	def set_plugin(self, plugin: "GlobalPlugin") -> None:
		"""Give the dialog a back-reference to the plugin so Start can call
		``plugin.start_server(mode)``."""
		self._plugin = plugin

	# -- UI construction --------------------------------------------------------

	def _build_ui(self) -> None:
		main_helper = guiHelper.BoxSizerHelper(self, orientation=wx.VERTICAL)

		# 1. Connection mode — use addLabeledControl so NVDA reads the combo
		#    items when arrowing (the label is properly associated for a11y).
		choices = [
			# Translators: Connection mode option: named pipe.
			_("Named pipe"),
			# Translators: Connection mode option: loopback TCP.
			_("TCP"),
		]
		# Translators: Label above the connection mode combo box.
		self._mode_combo = main_helper.addLabeledControl(
			_("Connection mode:"), wx.Choice, choices=choices
		)
		self._mode_combo.Bind(wx.EVT_CHOICE, self._on_mode_changed)

		# 2. Auto-start checkbox
		# Translators: Checkbox in the bridge dialog to start the bridge automatically when NVDA loads.
		self._auto_start_cb = main_helper.addItem(
			wx.CheckBox(self, label=_("Start bridge automatically when NVDA loads"))
		)
		self._auto_start_cb.Bind(wx.EVT_CHECKBOX, self._on_auto_start_changed)

		# 3. Button row (Start, Stop, Close)
		button_helper = guiHelper.ButtonHelper(wx.HORIZONTAL)

		# Translators: Button in the bridge dialog to start the server.
		self._start_btn = button_helper.addButton(self, label=_("&Start"))
		self._start_btn.Bind(wx.EVT_BUTTON, self._on_start)

		# Translators: Button in the bridge dialog to stop the server.
		self._stop_btn = button_helper.addButton(self, label=_("St&op"))
		self._stop_btn.Bind(wx.EVT_BUTTON, self._on_stop)

		# Translators: Button in the bridge dialog to close the dialog.
		close_btn = button_helper.addButton(self, label=_("&Close"))
		close_btn.Bind(wx.EVT_BUTTON, lambda evt: self._dismiss())

		main_helper.addItem(button_helper)

		# 4. Status bar — NVDA+End reads this.
		self._status_bar = wx.StatusBar(self)
		main_helper.addItem(self._status_bar, flag=wx.EXPAND)

		main_sizer = wx.BoxSizer(wx.VERTICAL)
		main_sizer.Add(main_helper.sizer, border=10, flag=wx.ALL)
		main_sizer.Fit(self)
		self.SetSizer(main_sizer)

	# -- init (one-shot, not on every refresh) -----------------------------------

	def _init_combo_from_config(self) -> None:
		"""Set the combo to the persisted mode from config.ini.

		Called once at dialog open. After this the combo tracks the user's
		choice independently — _refresh() never resets it.
		"""
		mode = self._config.get_connection_mode()
		self._mode_combo.SetSelection(_mode_to_combo_index(mode))

	# -- refresh ----------------------------------------------------------------

	def _refresh(self, *, announce: bool = True) -> None:
		"""Read server status and config, then update every control.

		Does NOT touch the combo selection — that belongs to the user while
		the dialog is open. When *announce* is True (the default), announces
		state transitions so the user hears "Bridge started", "Stopped",
		"Client connected", or "Client disconnected" regardless of who
		triggered the change.
		"""
		status = self._server.status
		new_state = status.state
		stopped = new_state is ServerState.STOPPED

		# Announce transitions before updating _last_state.
		if announce:
			self._announce_transition(self._last_state, new_state)
			self._last_state = new_state

		# Status bar: exactly three strings. The endpoint already encodes the
		# connection mode (pipe name or host:port).
		if new_state is ServerState.STOPPED:
			# Translators: Shown in the bridge dialog status bar when stopped.
			self._status_bar.SetStatusText(_("Stopped"))
		elif new_state is ServerState.LISTENING:
			endpoint = status.endpoint or "?"
			# Translators: Shown in the bridge dialog status bar when listening.
			# {endpoint} is the pipe name or host:port.
			self._status_bar.SetStatusText(_("Listening on {endpoint}").format(endpoint=endpoint))
		else:  # SESSION_ACTIVE
			# Translators: Shown in the bridge dialog status bar when a client is connected.
			self._status_bar.SetStatusText(_("Client connected"))

		# Combo: enabled only when stopped. While stopped the user can change
		# the mode; once listening or connected the mode is locked.
		self._mode_combo.Enable(stopped)

		# Buttons: Start only when stopped; Stop when not stopped.
		self._start_btn.Enable(stopped)
		self._stop_btn.Enable(not stopped)

		# Auto-start: read from config (it may have been toggled elsewhere).
		self._auto_start_cb.SetValue(self._config.get_auto_start())

	# -- announce ----------------------------------------------------------------

	@staticmethod
	def _announce_transition(old: ServerState | None, new: ServerState) -> None:
		"""Announce a state transition, if there is one. *old* is None on the
		first refresh after opening — that is not a transition."""
		if old is None:
			return
		if old is ServerState.STOPPED and new is ServerState.LISTENING:
			# Translators: Announced when the bridge starts listening.
			ui.message(_("Bridge started"))
		elif old is not ServerState.STOPPED and new is ServerState.STOPPED:
			# Translators: Announced when the bridge stops.
			ui.message(_("Bridge stopped"))
		elif new is ServerState.SESSION_ACTIVE:
			# Translators: Announced when a client connects.
			ui.message(_("Client connected"))
		elif old is ServerState.SESSION_ACTIVE and new is ServerState.LISTENING:
			# Translators: Announced when a client disconnects.
			ui.message(_("Client disconnected"))

	# -- event handlers ---------------------------------------------------------

	def _on_server_status(self, event: BridgeEvent) -> None:
		"""Called (on an arbitrary thread) when the server status changes.
		Marshal to the main thread so we can touch wx controls safely.
		Announces state transitions so the user hears what happened regardless
		of who triggered the change (Start button, panic gesture, client
		connecting, etc.)."""
		wx.CallAfter(self._handle_status_change, event)

	def _handle_status_change(self, event: BridgeEvent) -> None:
		"""Main-thread handler: refresh controls (which announces transitions)
		and steer focus to the most useful next control."""
		old = self._last_state
		new = event.payload.state
		self._refresh()

		# Steer focus to the most useful next control for this transition.
		if old is ServerState.STOPPED and new is ServerState.LISTENING:
			self._stop_btn.SetFocus()
		elif old is not ServerState.STOPPED and new is ServerState.STOPPED:
			self._mode_combo.SetFocus()

	def _on_mode_changed(self, evt: wx.CommandEvent) -> None:
		# The combo records the user's preference. No action needed here —
		# the actual listener rebuild and server restart happen only when
		# Start is pressed. Since the combo is disabled while not stopped,
		# the user must explicitly stop, choose, and start again.
		pass

	def _on_auto_start_changed(self, evt: wx.CommandEvent) -> None:
		self._config.set_auto_start(self._auto_start_cb.GetValue())

	def _on_start(self, evt: wx.CommandEvent) -> None:
		new_mode = _combo_index_to_mode(self._mode_combo.GetSelection())
		if self._plugin is not None:
			try:
				self._plugin.start_server(new_mode)
			except Exception:
				log.error("nvdaMcpBridge: could not start the bridge server", exc_info=True)
				return
		# The event bus callback handles refresh + announce + focus.

	def _on_stop(self, evt: wx.CommandEvent) -> None:
		self._server.stop()
		# The event bus callback handles refresh + announce.

	def _dismiss(self) -> None:
		"""Unsubscribe and end the modal loop. The single teardown path for
		Close button, ESC, and Alt+F4 — Close does NOT stop the server."""
		self._event_bus.unsubscribe(self._sub_token)
		self.EndModal(wx.ID_CANCEL)

	def _on_char_hook(self, evt: wx.KeyEvent) -> None:
		if evt.GetKeyCode() == wx.WXK_ESCAPE:
			self._dismiss()
		else:
			evt.Skip()

	def _on_close(self, evt: wx.CloseEvent) -> None:
		"""Alt+F4 / window close button — same teardown as _dismiss."""
		self._dismiss()
		evt.Skip()
