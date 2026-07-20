# nvdaMcpBridge -- nvdaMcpSpy: the silent-mode speech spy synth driver.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
# Modeled on NVDA's synthDrivers/silence.py and the SystemTestSpy speech spy
# (both GPL-2, the licence this addon carries).
#
# ROLE: an NVDA synth driver -- the NVDA edge. NVDA (synthDriverHandler), not our
#       wiring, instantiates this when silent mode swaps the synth to it, which is
#       why it meets the rest of the addon only at the pure spy_sink rendezvous.
#       On pyright's ignore list; validated by the 9c live-NVDA checklist.
# COLLABORATORS: spy_sink (delivers captured text to the active speech source);
#                synthDriverHandler.synthIndexReached / synthDoneSpeaking (so
#                NVDA's speech manager keeps advancing through the sequence, which
#                is the determinism silent mode exists for).
#
# Legitimate cross-package import: addonHandler.Addon.addToPackagePath extends
# both globalPlugins and synthDrivers with the addon's dirs, so this driver can
# import the plugin package's pure sink module by its full name.

from collections import OrderedDict

import synthDriverHandler
from speech.commands import IndexCommand

from globalPlugins.nvdaMcpBridge.adapters import spy_sink


class SynthDriver(synthDriverHandler.SynthDriver):
	"""Swallows audio, forwards spoken text to spy_sink, and drives NVDA's
	index/done notifications instantly so the speech manager never stalls."""

	name = spy_sink.SPY_SYNTH_NAME
	# Translators: Description of the NVDA MCP bridge speech-capture synthesizer.
	description = _("NVDA MCP bridge (speech capture)")

	@classmethod
	def check(cls):
		return True

	supportedSettings = frozenset()
	_availableVoices = OrderedDict({name: synthDriverHandler.VoiceInfo(name, description)})

	def speak(self, speechSequence):
		# The plain strings are the spoken words; SpeechCommand objects are not.
		spy_sink.notify([item for item in speechSequence if isinstance(item, str)])
		self.lastIndex = None
		for item in speechSequence:
			if isinstance(item, IndexCommand):
				self.lastIndex = item.index
				synthDriverHandler.synthIndexReached.notify(synth=self, index=item.index)
		# Fired after the text is delivered, so the source's exact-finish handler
		# sees a fully-populated buffer before it marks speech finished.
		synthDriverHandler.synthDoneSpeaking.notify(synth=self)

	def cancel(self):
		self.lastIndex = None

	def _get_voice(self):
		return self.name
