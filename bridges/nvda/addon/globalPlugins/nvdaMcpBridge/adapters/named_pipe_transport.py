# nvdaMcpBridge adapters -- NamedPipeTransport: the Transport leaf over a
# Windows named pipe.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# ROLE: LEAF adapter. IMPLEMENTS the Transport seam (adapters/ports/transport.py)
#       by doing real named-pipe IO via ctypes, and nothing else.
# USED BY: adapters/json_lines_channel.py, via the seam, never directly;
#          adapters/named_pipe_listener.py wraps each accepted connection in one
#          and imports the Win32 declarations below (kernel32, OVERLAPPED, the
#          error/wait constants) rather than redeclaring them -- same relationship
#          as tcp_listener.py importing DEFAULT_POLL_TIMEOUT from this file's TCP
#          counterpart.
# BUILT BY: adapters/named_pipe_listener.py wraps each accepted server-side
#           instance in one; `dial()` below builds the client-side counterpart,
#           used by tests/integration/test_named_pipe_session_roundtrip.py
#           exactly as socket.create_connection + SocketTransport play that role
#           for the TCP scenario, and by anything that later dials the bridge
#           over a pipe.
#
# Spec 0010. Every named-pipe handle opened with FILE_FLAG_OVERLAPPED must use
# OVERLAPPED structures for *every* ReadFile/WriteFile -- Windows requires it
# once a handle is opened that way -- so both recv() and sendall() below build
# one, even though sendall() does not need poll-timeout semantics (it waits
# INFINITE for GetOverlappedResult, the pipe analogue of a blocking socket
# sendall). recv()'s poll-timeout contract mirrors SocketTransport.recv exactly:
# WaitForSingleObject with a timeout stands in for socket settimeout.

from __future__ import annotations

import ctypes
import ctypes.wintypes as wintypes
import time
from typing import Final

from .ports.transport import Transport

#: How long recv blocks before reporting the idle poll timeout -- same default
#: and same meaning as socket_transport.DEFAULT_POLL_TIMEOUT.
DEFAULT_POLL_TIMEOUT: Final = 0.05

#: How long dial() retries ERROR_PIPE_BUSY / ERROR_FILE_NOT_FOUND before giving
#: up. Only used client-side (tests, and any future dialer).
DEFAULT_DIAL_TIMEOUT: Final = 5.0

BUFFER_SIZE: Final = 4096

# --- Win32 declarations -------------------------------------------------------
# Shared by named_pipe_listener.py (imported, not redeclared). Kept together in
# one place because a mismatched argtypes/restype here is a silent memory-safety
# bug, not a Python exception -- see the header note above.

KERNEL32 = ctypes.WinDLL("kernel32", use_last_error=True)
ADVAPI32 = ctypes.WinDLL("advapi32", use_last_error=True)

#: What CreateNamedPipeW/CreateFileW return on failure. A plain int: ctypes
#: unwraps a HANDLE-typed return value to a Python int (or None for a null
#: handle), so this is the exact value to compare against, not -1.
INVALID_HANDLE_VALUE: Final[int] = ctypes.c_void_p(-1).value or 0

ERROR_IO_PENDING: Final = 997
ERROR_PIPE_CONNECTED: Final = 535
ERROR_PIPE_BUSY: Final = 231
ERROR_BROKEN_PIPE: Final = 109
ERROR_PIPE_NOT_CONNECTED: Final = 233
ERROR_NO_DATA: Final = 232
ERROR_OPERATION_ABORTED: Final = 995
ERROR_FILE_NOT_FOUND: Final = 2

WAIT_OBJECT_0: Final = 0
WAIT_TIMEOUT: Final = 258

PIPE_ACCESS_DUPLEX: Final = 0x00000003
FILE_FLAG_OVERLAPPED: Final = 0x40000000
PIPE_TYPE_BYTE: Final = 0x00000000
PIPE_READMODE_BYTE: Final = 0x00000000
#: The pipe analogue of loopback-only binding (spec 0010, security posture).
PIPE_REJECT_REMOTE_CLIENTS: Final = 0x00000008
PIPE_UNLIMITED_INSTANCES: Final = 255
GENERIC_READ: Final = 0x80000000
GENERIC_WRITE: Final = 0x40000000
OPEN_EXISTING: Final = 3

#: A read/write end never gets EOF from anything but these -- the pipe
#: analogue of SocketTransport treating "any OTHER OSError" as a dropped peer.
_EOF_ERRORS: Final = frozenset(
    {ERROR_BROKEN_PIPE, ERROR_PIPE_NOT_CONNECTED, ERROR_NO_DATA, ERROR_OPERATION_ABORTED}
)


class OVERLAPPED(ctypes.Structure):
	"""The Win32 OVERLAPPED struct, flattened (Offset/OffsetHigh are unused for
	pipes; only hEvent matters here)."""

	_fields_ = (
		("Internal", ctypes.c_void_p),
		("InternalHigh", ctypes.c_void_p),
		("Offset", wintypes.DWORD),
		("OffsetHigh", wintypes.DWORD),
		("hEvent", wintypes.HANDLE),
	)


class SECURITY_ATTRIBUTES(ctypes.Structure):
	_fields_ = (
		("nLength", wintypes.DWORD),
		("lpSecurityDescriptor", ctypes.c_void_p),
		("bInheritHandle", wintypes.BOOL),
	)


KERNEL32.CreateNamedPipeW.argtypes = [
	wintypes.LPCWSTR,
	wintypes.DWORD,
	wintypes.DWORD,
	wintypes.DWORD,
	wintypes.DWORD,
	wintypes.DWORD,
	wintypes.DWORD,
	ctypes.c_void_p,
]
KERNEL32.CreateNamedPipeW.restype = wintypes.HANDLE

KERNEL32.CreateFileW.argtypes = [
	wintypes.LPCWSTR,
	wintypes.DWORD,
	wintypes.DWORD,
	ctypes.c_void_p,
	wintypes.DWORD,
	wintypes.DWORD,
	wintypes.HANDLE,
]
KERNEL32.CreateFileW.restype = wintypes.HANDLE

KERNEL32.CreateEventW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
KERNEL32.CreateEventW.restype = wintypes.HANDLE

KERNEL32.SetEvent.argtypes = [wintypes.HANDLE]
KERNEL32.SetEvent.restype = wintypes.BOOL

KERNEL32.ConnectNamedPipe.argtypes = [wintypes.HANDLE, ctypes.POINTER(OVERLAPPED)]
KERNEL32.ConnectNamedPipe.restype = wintypes.BOOL

KERNEL32.DisconnectNamedPipe.argtypes = [wintypes.HANDLE]
KERNEL32.DisconnectNamedPipe.restype = wintypes.BOOL

KERNEL32.WaitNamedPipeW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD]
KERNEL32.WaitNamedPipeW.restype = wintypes.BOOL

KERNEL32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
KERNEL32.WaitForSingleObject.restype = wintypes.DWORD

KERNEL32.GetOverlappedResult.argtypes = [
	wintypes.HANDLE,
	ctypes.POINTER(OVERLAPPED),
	ctypes.POINTER(wintypes.DWORD),
	wintypes.BOOL,
]
KERNEL32.GetOverlappedResult.restype = wintypes.BOOL

KERNEL32.ReadFile.argtypes = [
	wintypes.HANDLE,
	ctypes.c_void_p,
	wintypes.DWORD,
	ctypes.c_void_p,
	ctypes.POINTER(OVERLAPPED),
]
KERNEL32.ReadFile.restype = wintypes.BOOL

KERNEL32.WriteFile.argtypes = [
	wintypes.HANDLE,
	ctypes.c_void_p,
	wintypes.DWORD,
	ctypes.c_void_p,
	ctypes.POINTER(OVERLAPPED),
]
KERNEL32.WriteFile.restype = wintypes.BOOL

KERNEL32.CancelIoEx.argtypes = [wintypes.HANDLE, ctypes.POINTER(OVERLAPPED)]
KERNEL32.CancelIoEx.restype = wintypes.BOOL

KERNEL32.CloseHandle.argtypes = [wintypes.HANDLE]
KERNEL32.CloseHandle.restype = wintypes.BOOL

ADVAPI32.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [
	wintypes.LPCWSTR,
	wintypes.DWORD,
	ctypes.POINTER(ctypes.c_void_p),
	ctypes.c_void_p,
]
ADVAPI32.ConvertStringSecurityDescriptorToSecurityDescriptorW.restype = wintypes.BOOL

KERNEL32.LocalFree.argtypes = [ctypes.c_void_p]
KERNEL32.LocalFree.restype = ctypes.c_void_p


def create_event() -> int:
	"""A manual-reset, initially-unsignalled event, for one overlapped op."""
	handle = KERNEL32.CreateEventW(None, True, False, None)
	if not handle:
		raise ctypes.WinError(ctypes.get_last_error())
	return handle


def owner_only_security_attributes() -> SECURITY_ATTRIBUTES:
	"""Build once per listener and reused for every pipe instance it creates
	(spec 0010, security posture): DACL grants Generic All to the object's
	owner only (`OWNER RIGHTS`, SDDL ``OW``) -- every other local account is
	denied by omission, the pipe analogue of binding loopback-only.
	"""
	descriptor = ctypes.c_void_p()
	ok = ADVAPI32.ConvertStringSecurityDescriptorToSecurityDescriptorW(
		"D:(A;;GA;;;OW)", 1, ctypes.byref(descriptor), None
	)
	if not ok:
		raise ctypes.WinError(ctypes.get_last_error())
	attributes = SECURITY_ATTRIBUTES()
	attributes.nLength = ctypes.sizeof(SECURITY_ATTRIBUTES)
	attributes.lpSecurityDescriptor = descriptor
	attributes.bInheritHandle = False
	return attributes


def free_security_descriptor(attributes: SECURITY_ATTRIBUTES) -> None:
	if attributes.lpSecurityDescriptor:
		KERNEL32.LocalFree(attributes.lpSecurityDescriptor)
		attributes.lpSecurityDescriptor = None


class NamedPipeTransport(Transport):
	"""A byte pipe over one connected named-pipe handle, with a recv poll timeout.

	Wraps either side: a listener's accepted server instance, or a client
	handle from :func:`dial`. Both sides speak the same overlapped ReadFile/
	WriteFile protocol once connected, so one class serves both -- exactly as
	SocketTransport serves both ends of a TCP connection.
	"""

	def __init__(self, handle: int, *, poll_timeout: float = DEFAULT_POLL_TIMEOUT) -> None:
		self._handle = handle
		self._poll_timeout = poll_timeout
		self._closed = False

	def recv(self) -> bytes:
		"""Next chunk; ``b""`` at EOF; raises ``TimeoutError`` when idle.

		Mirrors SocketTransport.recv's contract exactly, built from primitives
		that do not offer it natively: an overlapped ReadFile plus
		WaitForSingleObject stands in for ``socket.settimeout``. A read that
		times out is cancelled (CancelIoEx) before raising, so it cannot
		complete later into a buffer nobody is looking at.
		"""
		if self._closed:
			return b""
		buf = ctypes.create_string_buffer(BUFFER_SIZE)
		overlapped = OVERLAPPED()
		event = create_event()
		overlapped.hEvent = event
		try:
			ok = KERNEL32.ReadFile(self._handle, buf, BUFFER_SIZE, None, ctypes.byref(overlapped))
			if not ok:
				err = ctypes.get_last_error()
				if err in _EOF_ERRORS:
					return b""
				if err != ERROR_IO_PENDING:
					raise ctypes.WinError(err)
				wait = KERNEL32.WaitForSingleObject(event, int(self._poll_timeout * 1000))
				if wait == WAIT_TIMEOUT:
					KERNEL32.CancelIoEx(self._handle, ctypes.byref(overlapped))
					transferred = wintypes.DWORD()
					# Drain the cancelled op so nothing is left pending on this
					# handle; the result (aborted, or a last-instant completion)
					# is irrelevant -- the poll timeout was already decided.
					KERNEL32.GetOverlappedResult(
						self._handle, ctypes.byref(overlapped), ctypes.byref(transferred), True
					)
					raise TimeoutError
			transferred = wintypes.DWORD()
			ok2 = KERNEL32.GetOverlappedResult(
				self._handle, ctypes.byref(overlapped), ctypes.byref(transferred), True
			)
			if not ok2:
				err = ctypes.get_last_error()
				if err in _EOF_ERRORS:
					return b""
				raise ctypes.WinError(err)
			return buf.raw[: transferred.value]
		finally:
			KERNEL32.CloseHandle(event)

	def sendall(self, data: bytes) -> None:
		"""Write every byte, blocking until each WriteFile completes -- the
		named-pipe analogue of a blocking socket's ``sendall``."""
		sent = 0
		while sent < len(data):
			chunk = data[sent:]
			buf = ctypes.create_string_buffer(chunk, len(chunk))
			overlapped = OVERLAPPED()
			event = create_event()
			overlapped.hEvent = event
			try:
				ok = KERNEL32.WriteFile(self._handle, buf, len(chunk), None, ctypes.byref(overlapped))
				if not ok:
					err = ctypes.get_last_error()
					if err != ERROR_IO_PENDING:
						raise ctypes.WinError(err)
				transferred = wintypes.DWORD()
				ok2 = KERNEL32.GetOverlappedResult(
					self._handle, ctypes.byref(overlapped), ctypes.byref(transferred), True
				)
				if not ok2:
					raise ctypes.WinError(ctypes.get_last_error())
				sent += transferred.value
			finally:
				KERNEL32.CloseHandle(event)

	def close(self) -> None:
		if self._closed:
			return
		self._closed = True
		KERNEL32.CancelIoEx(self._handle, None)
		# Only meaningful on a server-side instance; a client handle fails this
		# harmlessly (not a server end), which is fine -- best-effort only.
		KERNEL32.DisconnectNamedPipe(self._handle)
		KERNEL32.CloseHandle(self._handle)


def dial(pipe_name: str, *, timeout: float = DEFAULT_DIAL_TIMEOUT) -> NamedPipeTransport:
	"""Connect to a listening named pipe as a client, retrying while every
	instance is busy or not yet created, up to ``timeout``.

	The client-side counterpart to :class:`NamedPipeTransport` -- used by
	``tests/integration/test_named_pipe_session_roundtrip.py`` exactly as
	``socket.create_connection`` plays that role for the TCP scenario, and by
	anything that later dials the bridge over a pipe.
	"""
	deadline = time.monotonic() + timeout
	while True:
		handle = KERNEL32.CreateFileW(
			pipe_name,
			GENERIC_READ | GENERIC_WRITE,
			0,
			None,
			OPEN_EXISTING,
			FILE_FLAG_OVERLAPPED,
			None,
		)
		if handle != INVALID_HANDLE_VALUE:
			return NamedPipeTransport(handle)
		err = ctypes.get_last_error()
		if err not in (ERROR_PIPE_BUSY, ERROR_FILE_NOT_FOUND):
			raise ctypes.WinError(err)
		remaining = deadline - time.monotonic()
		if remaining <= 0:
			raise TimeoutError(f"no pipe instance of {pipe_name!r} became available within {timeout}s")
		if err == ERROR_PIPE_BUSY:
			KERNEL32.WaitNamedPipeW(pipe_name, int(min(remaining, 2.0) * 1000))
		else:
			# The pipe does not exist yet at all -- WaitNamedPipeW would also
			# fail with ERROR_FILE_NOT_FOUND, so just back off briefly and retry.
			time.sleep(min(remaining, 0.05))
