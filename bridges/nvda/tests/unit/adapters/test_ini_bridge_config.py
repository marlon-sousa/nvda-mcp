# nvdaMcpBridge tests -- unit tests for IniBridgeConfig against FakeConfigFile.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.

from __future__ import annotations

from nvdaMcpBridge.adapters.ini_bridge_config import IniBridgeConfig
from nvdaMcpBridge.domain.entities.connection_mode import DEFAULT, ConnectionMode
from fakes.config_file import FakeConfigFile
from fakes.log import FakeLog


# -- helpers ------------------------------------------------------------------

def _ini(mode: str = "namedPipe", auto_start: str = "false") -> str:
	return f"[nvdaMcpBridge]\nconnectionMode = {mode}\nautoStart = {auto_start}\n"


# -- defaults (no file) -------------------------------------------------------

def test_defaults_when_file_does_not_exist() -> None:
	cfg = IniBridgeConfig(FakeConfigFile(None), FakeLog())
	assert cfg.get_connection_mode() is DEFAULT
	assert cfg.get_auto_start() is False


def test_defaults_when_file_is_empty() -> None:
	cfg = IniBridgeConfig(FakeConfigFile(""), FakeLog())
	assert cfg.get_connection_mode() is DEFAULT
	assert cfg.get_auto_start() is False


# -- read ---------------------------------------------------------------------

def test_reads_connection_mode() -> None:
	cfg = IniBridgeConfig(FakeConfigFile(_ini(mode="loopbackTcp")), FakeLog())
	assert cfg.get_connection_mode() is ConnectionMode.LOOPBACK_TCP


def test_reads_auto_start_true() -> None:
	cfg = IniBridgeConfig(FakeConfigFile(_ini(auto_start="true")), FakeLog())
	assert cfg.get_auto_start() is True


def test_unrecognised_mode_falls_back_to_default() -> None:
	cfg = IniBridgeConfig(FakeConfigFile(_ini(mode="garbage")), FakeLog())
	assert cfg.get_connection_mode() is DEFAULT


# -- write --------------------------------------------------------------------

def test_writes_connection_mode() -> None:
	f = FakeConfigFile(_ini())
	cfg = IniBridgeConfig(f, FakeLog())
	cfg.set_connection_mode(ConnectionMode.LOOPBACK_TCP)
	assert "connectionmode = loopbacktcp" in (f.read() or "").lower()


def test_writes_auto_start() -> None:
	f = FakeConfigFile(_ini())
	cfg = IniBridgeConfig(f, FakeLog())
	cfg.set_auto_start(True)
	assert "autostart = true" in (f.read() or "").lower()


# -- corrupt file -------------------------------------------------------------

def test_corrupt_file_returns_defaults() -> None:
	cfg = IniBridgeConfig(FakeConfigFile("this is not valid ini {{{"), FakeLog())
	assert cfg.get_connection_mode() is DEFAULT
	assert cfg.get_auto_start() is False


# -- round-trip ---------------------------------------------------------------

def test_round_trip_connection_mode() -> None:
	f = FakeConfigFile(None)
	cfg = IniBridgeConfig(f, FakeLog())
	cfg.set_connection_mode(ConnectionMode.LOOPBACK_TCP)
	assert cfg.get_connection_mode() is ConnectionMode.LOOPBACK_TCP


def test_round_trip_auto_start() -> None:
	f = FakeConfigFile(None)
	cfg = IniBridgeConfig(f, FakeLog())
	cfg.set_auto_start(True)
	assert cfg.get_auto_start() is True
