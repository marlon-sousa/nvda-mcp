# nvdaMcpBridge adapters -- concrete implementations of the domain ports.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# One class per file. This is the ONLY package allowed to import NVDA (and the
# OS / real IO). Files that import NVDA are listed in pyright's ``ignore`` (see
# pyproject.toml) because the domain they serve is already strict-checked and
# they are validated by the live-NVDA integration tests; the pure ones here
# (clock, file transcript) carry no NVDA import and stay fully type-checked.
