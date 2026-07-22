# nvdaMcpBridge adapters -- NamedPipeListener: the Listener leaf over a Windows
# named pipe.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# ROLE: LEAF adapter. IMPLEMENTS the Listener seam (adapters/ports/listener.py)
#       via ctypes named-pipe calls, and nothing else.
# USED BY: adapters/bridge_server.py, via the seam, never directly. Not yet
#          built by plugin.py -- entry 9.1b (the control dialog) picks between
#          this and TcpListener; spec 0010 only proves the seam works.
# BUILT BY: tests/integration/test_named_pipe_session_roundtrip.py today; the
#           9.1b composition root once the GUI/config lands.
#
# Local-machine-only by construction (spec 0010, security posture):
# PIPE_REJECT_REMOTE_CLIENTS on every instance, plus an owner-only DACL built
# once in open() and reused for every instance -- the pipe analogue of
# TcpListener binding 127.0.0.1 only.
#
# Unlike the TCP leaf, this one is not decision-free -- overlapped I/O needs a
# real state machine -- so it earns its correctness from
# test_named_pipe_session_roundtrip.py (a real pipe, no NVDA), the same tier of
# proof 9a's socket scenario gave TcpListener, rather than from being "too
# simple to get wrong".

from __future__ import annotations

import ctypes
import ctypes.wintypes as wintypes

from .named_pipe_transport import (
	BUFFER_SIZE,
	ERROR_IO_PENDING,
	ERROR_PIPE_CONNECTED,
	FILE_FLAG_OVERLAPPED,
	INVALID_HANDLE_VALUE,
	KERNEL32,
	PIPE_ACCESS_DUPLEX,
	PIPE_READMODE_BYTE,
	PIPE_REJECT_REMOTE_CLIENTS,
	PIPE_TYPE_BYTE,
	PIPE_UNLIMITED_INSTANCES,
	WAIT_OBJECT_0,
	WAIT_TIMEOUT,
	OVERLAPPED,
	SECURITY_ATTRIBUTES,
	NamedPipeTransport,
	create_event,
	free_security_descriptor,
	owner_only_security_attributes,
)
from .ports.listener import Listener, ListenerClosed
from .ports.transport import Transport
from .named_pipe_transport import DEFAULT_POLL_TIMEOUT as _DEFAULT_RECV_TIMEOUT

#: Poll window for accept: how long it blocks before reporting TimeoutError, so
#: the server thread can notice a stop request -- same meaning as
#: tcp_listener.DEFAULT_ACCEPT_TIMEOUT.
DEFAULT_ACCEPT_TIMEOUT: float = 0.5


class _PendingInstance:
	"""One armed-but-not-yet-connected pipe instance, plus the OVERLAPPED/event
	pair its outstanding ConnectNamedPipe call is writing into.

	A plain holder, not a dataclass -- it exists solely to keep the OVERLAPPED
	struct and event alive for the lifetime of the outstanding async op (letting
	either get garbage-collected while Windows still holds a pointer to the
	OVERLAPPED would be a real memory-safety bug, not a Python exception).
	"""

	def __init__(self, handle: int, event: int, overlapped: OVERLAPPED) -> None:
		self.handle = handle
		self.event = event
		self.overlapped = overlapped


class NamedPipeListener(Listener):
	"""A local-machine-only named-pipe listener yielding one connection at a time."""

	def __init__(
		self,
		pipe_name: str,
		*,
		accept_timeout: float = DEFAULT_ACCEPT_TIMEOUT,
		recv_timeout: float = _DEFAULT_RECV_TIMEOUT,
	) -> None:
		self._pipe_name = pipe_name
		self._accept_timeout = accept_timeout
		self._recv_timeout = recv_timeout
		self._security_attributes: SECURITY_ATTRIBUTES | None = None
		self._pending: _PendingInstance | None = None
		self._closed = True

	@property
	def endpoint(self) -> str:
		return self._pipe_name

	def open(self) -> None:
		self._security_attributes = owner_only_security_attributes()
		self._closed = False
		self._pending = self._create_pending_instance()

	def accept(self) -> Transport:
		if self._closed:
			raise ListenerClosed
		if self._pending is None:
			self._pending = self._create_pending_instance()
		pending = self._pending

		wait = KERNEL32.WaitForSingleObject(pending.event, int(self._accept_timeout * 1000))
		if wait == WAIT_TIMEOUT:
			raise TimeoutError
		if self._closed:
			# close() ran concurrently and already cleaned up `pending` -- do
			# not touch its handles again.
			raise ListenerClosed
		if wait != WAIT_OBJECT_0:
			raise ctypes.WinError(ctypes.get_last_error())

		transferred = wintypes.DWORD()
		ok = KERNEL32.GetOverlappedResult(
			pending.handle, ctypes.byref(pending.overlapped), ctypes.byref(transferred), False
		)
		self._pending = None
		if not ok:
			err = ctypes.get_last_error()
			KERNEL32.CloseHandle(pending.handle)
			KERNEL32.CloseHandle(pending.event)
			if self._closed:
				raise ListenerClosed
			raise ctypes.WinError(err)

		transport = NamedPipeTransport(pending.handle, poll_timeout=self._recv_timeout)
		# Arm the next instance before returning, so one client may queue while
		# this connection's session runs -- the pipe analogue of TCP's
		# listen(1) backlog.
		self._pending = self._create_pending_instance()
		return transport

	def close(self) -> None:
		self._closed = True
		pending = self._pending
		self._pending = None
		if pending is not None:
			KERNEL32.CancelIoEx(pending.handle, ctypes.byref(pending.overlapped))
			transferred = wintypes.DWORD()
			KERNEL32.GetOverlappedResult(
				pending.handle, ctypes.byref(pending.overlapped), ctypes.byref(transferred), True
			)
			KERNEL32.CloseHandle(pending.handle)
			KERNEL32.CloseHandle(pending.event)
		if self._security_attributes is not None:
			free_security_descriptor(self._security_attributes)
			self._security_attributes = None

	# -- internals ------------------------------------------------------------

	def _create_pending_instance(self) -> _PendingInstance:
		assert self._security_attributes is not None, "open() must run before accept()"
		handle = KERNEL32.CreateNamedPipeW(
			self._pipe_name,
			PIPE_ACCESS_DUPLEX | FILE_FLAG_OVERLAPPED,
			PIPE_TYPE_BYTE | PIPE_READMODE_BYTE | PIPE_REJECT_REMOTE_CLIENTS,
			PIPE_UNLIMITED_INSTANCES,
			BUFFER_SIZE,
			BUFFER_SIZE,
			0,  # default timeout
			ctypes.byref(self._security_attributes),
		)
		if handle == INVALID_HANDLE_VALUE:
			raise ctypes.WinError(ctypes.get_last_error())
		event = create_event()
		overlapped = OVERLAPPED()
		overlapped.hEvent = event
		pending = _PendingInstance(handle, event, overlapped)

		ok = KERNEL32.ConnectNamedPipe(handle, ctypes.byref(overlapped))
		if not ok:
			err = ctypes.get_last_error()
			if err == ERROR_PIPE_CONNECTED:
				# A client already dialled in between CreateNamedPipeW and
				# ConnectNamedPipe -- signal the event ourselves so the accept
				# poll sees it as already-connected.
				KERNEL32.SetEvent(event)
			elif err != ERROR_IO_PENDING:
				KERNEL32.CloseHandle(handle)
				KERNEL32.CloseHandle(event)
				raise ctypes.WinError(err)
		return pending
