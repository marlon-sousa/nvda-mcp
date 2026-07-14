# nvda-mcp

An MCP server that lets an AI agent **drive NVDA**: send keyboard gestures,
read back what NVDA speaks (and brailles), and introspect its state. The first
use case is **functional testing of NVDA add-ons** — replacing manual testing —
but the same primitives support a wider range of agent-driven NVDA workflows.

See [specs/0001-agent-driven-nvda-over-mcp.md](specs/0001-agent-driven-nvda-over-mcp.md)
for the full design, decisions and milestones. Design specs live in
[specs/](specs/), numbered RFC-style (`NNNN-title.md`); new features add a new
spec alongside.

## Architecture

```
MCP client (Claude Code, ...)
   │  MCP over stdio
   ▼
nvda-mcp server            — Python package (mcpServer/), official mcp SDK / FastMCP
   │  JSON lines over TCP, 127.0.0.1 only
   ▼
nvdaMcpBridge              — NVDA add-on (bridgeAddon/): global plugin + spy synth
```

The server survives NVDA restarts (restarting NVDA is itself a test operation),
and NVDA's embedded Python is a poor host for an asyncio MCP stdio server, so
the two halves are split and meet only at the loopback socket.

## Repository layout

| Path | What |
|---|---|
| [shared/](shared/) | Canonical **stdlib-only** JSON-lines wire protocol (`nvda-mcp-wire`), shared verbatim by both halves and unit-tested once. |
| [mcpServer/](mcpServer/) | The MCP server (`nvda-mcp`): MCP tool call → bridge command → result. |
| [bridgeAddon/](bridgeAddon/) | The NVDA add-on (`nvdaMcpBridge`), built with scons. Its build copies `shared/`'s protocol module in, so bridge and server can never drift. |
| [specs/](specs/) | Numbered design specs (RFC-style). |

## Development

Requires [uv](https://docs.astral.sh/uv/) and (for the bridge type-check) a
sibling NVDA 2026.1 source checkout at `../nvda`.

```sh
# Shared wire contract (no NVDA needed)
uv run --directory shared pytest
uv run --directory shared pyright

# Server (no NVDA needed; tests use a fake bridge)
uv run --directory mcpServer pytest
uv run --directory mcpServer pyright

# Bridge add-on (type-checks against the NVDA source checkout)
py -3.13 bridgeAddon/sync_shared.py
uv run --directory bridgeAddon pyright   # or: cd bridgeAddon && scons   to build the .nvda-addon
```

Wire the server into Claude Code from source:

```sh
claude mcp add --scope user nvda -- uv run --directory C:\projects\nvda-mcp\mcpServer nvda-mcp
```

## Status

Implemented per milestone (see [the spec](specs/0001-agent-driven-nvda-over-mcp.md)):

- [x] **Session A — foundation**: repo layout, shared wire protocol + tests, tooling/CI.
- [ ] Session B — bridge core logic (buffer, session state machine, framing, transcript).
- [ ] Session C — bridge ↔ NVDA adapters, spy synth, live validation (milestones 1–3).
- [ ] Session D — MCP server + v1 tools (milestone 4).
- [ ] Session E — introspection + real-world validation (milestones 5–6).
- [ ] Session F — packaging & release (milestone 7).

## License

GPL v2. See [LICENSE](LICENSE) / COPYING.txt. The bridge's spy synth driver is
adapted from NVDA's own GPL-2 system-test suite.
