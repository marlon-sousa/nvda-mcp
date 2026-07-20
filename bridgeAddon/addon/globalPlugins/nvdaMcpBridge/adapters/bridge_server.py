# nvdaMcpBridge adapters -- BridgeServer: the start/stop connection controller.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# ROLE: an adapter-layer CONTROLLER -- the orchestrator of the connection edge.
#       It is NOT in the domain: its collaborators are adapter seams (Listener,
#       Transport) the domain must never see, so it lives out here with them,
#       the same doctrine as JsonLinesChannel (an upper adapter holding every
#       decision, unit-tested against a fake seam) one level further out.
# HOLDS: a Listener (the accepting seam) and a session_factory that turns an
#        accepted Transport into a Session; it owns the server thread.
# BUILT BY: plugin.py in session C (real TcpListener + a factory closing over
#           wiring.build_session); by tests with a FakeListener + fake factory.
# USED BY: the plugin now (start on init, stop on terminate/panic); the entry
#          9.1 control dialog next -- which is why start/stop and an observable
#          `status` snapshot are the whole public surface.
#
# It owns exactly the connection lifecycle and touches no synths: the Session's
# teardown promise (restore the user's synth in a finally) is the Session's job.
# One session at a time: accept -> build -> run() inline on the server thread ->
# back to accepting. stop() asks any live session to tear down (the one
# cross-thread call the Session permits), closes the listener to unblock accept,
# and joins the thread.

from __future__ import annotations

import enum
import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

from ..domain.controllers.teardown_reason import TeardownReason
from .ports.listener import ListenerClosed

if TYPE_CHECKING:
	from ..domain.controllers.session import Session
	from .ports.listener import Listener
	from .ports.transport import Transport

#: What plugin.py builds a session with (nvda version etc. are bound in the
#: closure); BridgeServer only needs "a Transport becomes a Session".
SessionFactory = Callable[["Transport"], "Session"]


class ServerState(enum.Enum):
	"""The observable state entry 9.1's dialog reflects (plain Enum: it never
	crosses the wire)."""

	STOPPED = "stopped"
	LISTENING = "listening"
	SESSION_ACTIVE = "session-active"


@dataclass(frozen=True)
class ServerStatus:
	"""A thread-safe snapshot of the server. ``endpoint`` is the accepting
	address while listening/active, and ``None`` when stopped."""

	state: ServerState
	endpoint: str | None


class BridgeServer:
	"""Runs the accept loop on its own thread; start/stop with an observable status."""

	def __init__(self, listener: Listener, session_factory: SessionFactory) -> None:
		self._listener = listener
		self._session_factory = session_factory

		# One lock guards every field the server thread and a caller thread both
		# touch: the status pair, the live session, the thread handle, the flag.
		self._lock = threading.Lock()
		self._state = ServerState.STOPPED
		self._endpoint: str | None = None
		self._active_session: Session | None = None
		self._thread: threading.Thread | None = None
		self._stopping = False

	# -- public API ----------------------------------------------------------

	@property
	def status(self) -> ServerStatus:
		with self._lock:
			return ServerStatus(self._state, self._endpoint)

	def start(self) -> None:
		"""Bind, report LISTENING, and spawn the accept loop. A no-op if already
		running. Binding happens on the caller's thread so a bind failure (e.g.
		port in use) surfaces here rather than dying silently in the thread."""
		with self._lock:
			if self._state is not ServerState.STOPPED:
				return
			self._listener.open()
			self._endpoint = self._listener.endpoint
			self._state = ServerState.LISTENING
			self._stopping = False
			self._thread = threading.Thread(
				target=self._serve, name="nvdaMcpBridge-server", daemon=True
			)
			self._thread.start()

	def stop(self) -> None:
		"""Stop accepting and end any live session; idempotent, and blocking until
		the server thread has joined and the state is STOPPED.

		Must not be called from the server thread itself (it joins that thread) --
		it is driven from the plugin's terminate/panic path and the 9.1 dialog,
		never from inside a session.
		"""
		with self._lock:
			thread = self._thread
			session = self._active_session
			self._stopping = True
		if session is not None:
			session.request_teardown(TeardownReason.EXTERNAL)
		self._listener.close()
		if thread is not None:
			thread.join()
		with self._lock:
			self._state = ServerState.STOPPED
			self._endpoint = None
			self._active_session = None
			self._thread = None
			self._stopping = False

	# -- the accept loop (runs on the server thread) -------------------------

	def _serve(self) -> None:
		try:
			while not self._is_stopping():
				try:
					transport = self._listener.accept()
				except TimeoutError:
					continue  # idle poll; loop back and re-check the stop flag
				except ListenerClosed:
					break  # stop() closed the listener
				except Exception:
					break  # an unexpected listener fault: stop, do not spin
				self._run_session(transport)
		finally:
			# An abnormal exit (a listener fault, not stop()) still has to leave an
			# honest status and release the socket; the normal stop() path already
			# owns both, so only act when it was not stop() that got us here.
			if not self._is_stopping():
				self._listener.close()
				with self._lock:
					self._state = ServerState.STOPPED
					self._endpoint = None
					self._active_session = None

	def _run_session(self, transport: Transport) -> None:
		session = self._session_factory(transport)
		with self._lock:
			self._active_session = session
			self._state = ServerState.SESSION_ACTIVE
			stopping = self._stopping
		# stop() may have raced in before we registered the session; if so it saw
		# no active session to tear down, so we do it ourselves and run() returns
		# at once. run() executes inline here -- one session at a time by design.
		if stopping:
			session.request_teardown(TeardownReason.EXTERNAL)
		try:
			session.run()
		finally:
			with self._lock:
				self._active_session = None
				if not self._stopping:
					self._state = ServerState.LISTENING

	def _is_stopping(self) -> bool:
		with self._lock:
			return self._stopping
