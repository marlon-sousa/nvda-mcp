# nvdaMcpBridge domain -- the command registry: the explicit command -> handler map.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# ROLE: the composition point for command handlers -- a hand-written map, read
# top to bottom, of every wire command to the one handler that serves it. This is
# deliberately NOT a DI container and NOT reflection/decorator auto-registration
# (AGENTS.md, Decided): the graph is visible here, and a compile-time wiring
# mistake is a pyright error, not a runtime surprise inside NVDA.
# BUILT BY: wiring.py in production (session C); the test builder in unit tests.
# USED BY: the Session, which only ever looks a command up and calls execute.
#
# Handlers are stateless singletons: the per-session state lives in the
# SessionContext handed to execute, so one map serves every session. hello is the
# exception -- it needs the AdapterFactory and NVDA version to build a session --
# so those are this builder's only parameters.

from __future__ import annotations

from typing import TYPE_CHECKING

from .... import protocol
from .bye import ByeHandler
from .command_handler import CommandHandler
from .echo import EchoHandler
from .get_braille import GetBrailleHandler
from .get_last_speech import GetLastSpeechHandler
from .get_next_speech_index import GetNextSpeechIndexHandler
from .get_speech import GetSpeechHandler
from .hello import HelloHandler
from .not_implemented import NotImplementedHandler
from .ping import PingHandler
from .press_gesture import PressGestureHandler
from .wait_for_speech import WaitForSpeechHandler
from .wait_for_speech_to_finish import WaitForSpeechToFinishHandler

if TYPE_CHECKING:
	from ...ports.adapter_factory import AdapterFactory


def build_command_registry(factory: AdapterFactory, nvda_version: str) -> dict[str, CommandHandler]:
	"""Construct the command -> handler map for a bridge (one per process)."""
	not_implemented = NotImplementedHandler()
	registry: dict[str, CommandHandler] = {
		protocol.Command.HELLO: HelloHandler(factory, nvda_version),
		protocol.Command.BYE: ByeHandler(),
		protocol.Command.PING: PingHandler(),
		protocol.Command.ECHO: EchoHandler(),
		protocol.Command.PRESS_GESTURE: PressGestureHandler(),
		protocol.Command.GET_SPEECH: GetSpeechHandler(),
		protocol.Command.GET_LAST_SPEECH: GetLastSpeechHandler(),
		protocol.Command.GET_NEXT_SPEECH_INDEX: GetNextSpeechIndexHandler(),
		protocol.Command.WAIT_FOR_SPEECH: WaitForSpeechHandler(),
		protocol.Command.WAIT_FOR_SPEECH_TO_FINISH: WaitForSpeechToFinishHandler(),
		protocol.Command.GET_BRAILLE: GetBrailleHandler(),
		# Ports arrive in session E; until then they answer a clean CommandError.
		protocol.Command.GET_FOCUS_INFO: not_implemented,
		protocol.Command.GET_STATE: not_implemented,
		protocol.Command.GET_CONFIG: not_implemented,
		protocol.Command.SET_CONFIG: not_implemented,
	}
	return registry
