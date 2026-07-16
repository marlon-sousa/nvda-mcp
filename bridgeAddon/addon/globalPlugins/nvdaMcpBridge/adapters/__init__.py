# nvdaMcpBridge adapters -- concrete implementations of the domain ports.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# One class per file. This is the ONLY package allowed to import NVDA, the OS,
# sockets or files. Each file's header states: which port it IMPLEMENTS, which
# seam it DEPENDS ON, and who BUILDS it.
#
# Adapters are LAYERED so the untestable part shrinks to almost nothing:
#
#   FileTranscript   (Transcript port)     -> FileWriter seam -> TextFileWriter (leaf)
#   JsonLinesChannel (MessageChannel port) -> Transport  seam -> SocketTransport (leaf, C)
#
# The upper adapter holds every decision (transcript vocabulary, framing) and is
# unit-tested precisely against a fake seam; the leaf makes no decisions and
# does nothing but call the OS. See adapters/ports/ for the seams.
#
# Files that import NVDA are listed in pyright's `ignore` (see pyproject.toml)
# because the domain they serve is already strict-checked and they are validated
# by the live-NVDA integration tests; the pure ones here stay fully type-checked.
