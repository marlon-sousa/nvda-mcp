# nvdaMcpBridge adapters -- seams BETWEEN adapters.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# These interfaces are NOT domain ports: the domain never sees them. They exist
# so an adapter can be layered over a smaller, dumber adapter and stay precisely
# testable -- e.g. FileTranscript (vocabulary/formatting) over a FileWriter (raw
# file IO), JsonLinesChannel (framing) over a Transport (raw bytes).
#
# The pattern: push the untestable IO down to a LEAF adapter that is a handful
# of lines and does nothing but call the OS, and keep every decision above it
# behind one of these seams, where a fake makes the test exact.
#
# Same rules as the domain ports: abc.ABC + @abstractmethod, one per file.
# No re-exports -- import each from its own file.
