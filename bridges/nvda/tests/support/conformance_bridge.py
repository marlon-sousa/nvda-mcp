# nvdaMcpBridge tests -- a REAL bridge, started from outside pytest.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# ROLE: test scaffolding (a builder, not a port double -- hence tests/support/,
# per AGENTS.md). It is the headless bridge of
# tests/integration/test_socket_session_roundtrip.py and
# test_named_pipe_session_roundtrip.py -- a real BridgeServer, a real listener, a
# real Session, a FakeAdapterFactory in place of NVDA -- made STARTABLE AS A
# PROCESS so something other than pytest can drive it.
# USED BY: server/tests/conformance/ (spec 0013, deliverable 19), whose Go
# conformance job launches this script and then drives it with the real MCP
# server.
#
# WHY IT EXISTS. Every other test of the Go server drives a Go fake bridge, which
# encodes frames with the same generated binding the server decodes them with --
# so a bug IN THE BINDING is invisible there: both sides would be wrong together,
# in agreement. Only the real Python implementation of specs/wire/v1/ can catch
# that, and this is how the Go side reaches it. It is the successor to the
# same-bytes drift guarantee the two halves had while both were Python.
#
# The protocol with its driver is deliberately tiny, because a driver in another
# language has to implement it: start us with --transport, read ONE JSON line
# from stdout naming the endpoint we are listening on, then close our stdin to
# stop us. Nothing else is ever written to stdout.
#
# NVDA is not involved and is not needed: the fakes stand in for the reader, and
# what is under test is the WIRE, not NVDA's behaviour (that is entry 11).

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Sequence

_SUPPORT_DIR = Path(__file__).resolve().parent
_TESTS_DIR = _SUPPORT_DIR.parent
_BRIDGE_ROOT = _TESTS_DIR.parent
_GLOBAL_PLUGINS = _BRIDGE_ROOT / "addon" / "globalPlugins"


def _bootstrap() -> None:
	"""Make the addon package importable, exactly as tests/conftest.py does.

	Self-contained on purpose: the driver is a Go test, so there is no conftest
	to run first and no ordering for anyone to get wrong. ``protocol.py`` is a
	gitignored build artifact, so it is synced here too -- which also means the
	bytes this bridge speaks the wire with are the shipped ones.
	"""
	spec = importlib.util.spec_from_file_location("_sync_shared", _BRIDGE_ROOT / "sync_shared.py")
	assert spec is not None and spec.loader is not None
	module = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(module)
	module.sync()
	for path in (_GLOBAL_PLUGINS, _TESTS_DIR):
		if str(path) not in sys.path:
			sys.path.insert(0, str(path))


_bootstrap()

# Imported after the bootstrap above on purpose: neither the addon package nor
# the fakes are importable until globalPlugins and tests/ are on sys.path.
from fakes.adapter_factory import FakeAdapterFactory  # noqa: E402
from fakes.announcer import FakeAnnouncer  # noqa: E402
from fakes.log_capture import FakeLogCapture  # noqa: E402
from fakes.session_signals import FakeSessionSignals  # noqa: E402

from nvdaMcpBridge.adapters.bridge_server import BridgeServer, SessionFactory  # noqa: E402
from nvdaMcpBridge.adapters.ports.listener import Listener  # noqa: E402
from nvdaMcpBridge.adapters.ports.transport import Transport  # noqa: E402
from nvdaMcpBridge.adapters.tcp_listener import TcpListener  # noqa: E402
from nvdaMcpBridge.domain.controllers.session import Session  # noqa: E402
from nvdaMcpBridge.wiring import build_session  # noqa: E402

#: The reader version this harness announces. Not a real NVDA version, and
#: deliberately recognisable: an assertion that matched it by accident against a
#: live NVDA on the same machine would be a false pass.
READER_VERSION = "2026.1.0-conformance"

#: The fake NVDA's script: pressing this gesture makes it speak these lines,
#: through the real speech buffer, exactly as a real key press would. It is what
#: lets the driver prove a whole "press, then read what it said" round trip
#: across the language boundary.
SCRIPTED_SPEECH: dict[str, list[str]] = {
	"kb:NVDA+f7": ["Elements list dialog", "Links radio button checked"],
}

#: What is already on the braille display when capture starts, so getBraille has
#: something real to return without a live NVDA.
INITIAL_BRAILLE = ["elements lst dlg"]


def _build_listener(transport: str) -> Listener:
	"""The real listener for one transport, on an endpoint nothing else owns."""
	if transport == "tcp":
		# Port 0: the OS picks a free one, so parallel runs cannot collide.
		return TcpListener("127.0.0.1", 0)
	# Imported here, not at module scope: the named-pipe leaf is ctypes/Win32,
	# so importing it would make this whole harness Windows-only when the TCP
	# half of the conformance run is not.
	from nvdaMcpBridge.adapters.named_pipe_listener import NamedPipeListener

	# The pipe analogue of port 0, and it carries this harness's own name so a
	# run can neither collide with a real installed bridge nor be satisfied by
	# one.
	return NamedPipeListener(rf"\\.\pipe\nvdaMcpBridgeConformance-{uuid.uuid4().hex}")


def _endpoint_spec(transport: str, endpoint: str) -> str:
	"""The accepting endpoint, spelled the way the SERVER's configuration does.

	The bridge reports ``127.0.0.1:8765`` or ``\\\\.\\pipe\\name``; the server's
	``--reader`` flag wants ``tcp:127.0.0.1:8765`` or ``pipe:name``. Translating
	here keeps the driver from having to know either spelling.
	"""
	if transport == "tcp":
		return f"tcp:{endpoint}"
	return "pipe:" + endpoint.rsplit("\\", 1)[-1]


def _session_factory(logs_dir: Path) -> SessionFactory:
	"""A fresh fake NVDA per session, wired into the real session stack."""

	def build(transport: Transport) -> Session:
		factory = FakeAdapterFactory(speech=SCRIPTED_SPEECH)
		factory.braille_source.initial = list(INITIAL_BRAILLE)
		return build_session(
			transport,
			factory,
			logs_dir,
			READER_VERSION,
			FakeSessionSignals(),
			FakeAnnouncer(),
			FakeLogCapture(),
		)

	return build


def main(argv: Sequence[str] | None = None) -> int:
	parser = argparse.ArgumentParser(description="Run a headless NVDA bridge for conformance testing.")
	parser.add_argument("--transport", choices=("pipe", "tcp"), required=True)
	parser.add_argument(
		"--logs-dir",
		default=None,
		help="where session transcripts go; a temporary directory by default",
	)
	args = parser.parse_args(argv)

	transport: str = args.transport
	logs_dir = Path(args.logs_dir) if args.logs_dir else Path(tempfile.mkdtemp(prefix="nvda-mcp-conformance-"))

	server = BridgeServer(_build_listener(transport), _session_factory(logs_dir))
	server.start()
	endpoint = server.status.endpoint
	if endpoint is None:
		server.stop()
		sys.stderr.write("the bridge started but reported no endpoint\n")
		return 1

	try:
		# THE handshake with the driver: one JSON line, then silence. Flushed
		# because the driver blocks on this line and our stdout is a pipe.
		sys.stdout.write(json.dumps({"endpoint": _endpoint_spec(transport, endpoint)}) + "\n")
		sys.stdout.flush()
		sys.stderr.write(f"conformance bridge listening on {endpoint}; transcripts in {logs_dir}\n")
		sys.stderr.flush()

		# Stdin EOF is the stop signal, rather than a signal handler: the driver
		# closing our stdin works identically on every platform, and it cannot
		# leave us alive if the driver dies -- which a kill sent to an
		# intermediate launcher process could.
		sys.stdin.read()
	except KeyboardInterrupt:
		pass
	finally:
		server.stop()
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
