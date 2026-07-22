# nvdaMcpBridge domain -- command handlers: one controller per wire command.
# Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
#
# ROLE: the per-command orchestrators. Each is a CommandHandler (a controller in
# the four-roles vocabulary -- it runs one use case over ports/entities), one
# class per file, mirrored one-for-one by a test. The Session is just the
# dispatcher: it reads a message, looks the command up in an explicit registry,
# and calls handler.execute(ctx, request); the handler owns that command's logic.
#
# DEPENDS ON: the SessionContext (its per-session collaborators) and the domain
# ports/entities -- never on NVDA. A handler is testable with a hand-built
# SessionContext and no Session at all.
#
# No re-exports -- import each handler and build the registry explicitly in
# registry.py (composition, not a DI container).
