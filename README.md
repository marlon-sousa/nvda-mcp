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

The chain, top to bottom — each item talks only to the next:

1. An MCP client (Claude Code, …) speaks MCP over stdio to the server.
2. The `nvda-mcp` server — a Python package ([mcpServer/](mcpServer/)) on the
   official `mcp` SDK (FastMCP) — speaks JSON lines over TCP, 127.0.0.1 only,
   to the bridge.
3. `nvdaMcpBridge` — an NVDA add-on ([bridges/nvda/](bridges/nvda/)): global
   plugin + spy synth driver — drives NVDA itself.

The server survives NVDA restarts (restarting NVDA is itself a test operation),
and NVDA's embedded Python is a poor host for an asyncio MCP stdio server, so
the two halves are split and meet only at the loopback socket.

## Repository layout

| Path | What |
|---|---|
| [shared/](shared/) | Canonical **stdlib-only** JSON-lines wire protocol (`nvda-mcp-wire`), shared verbatim by both halves and unit-tested once. |
| [mcpServer/](mcpServer/) | The MCP server (`nvda-mcp`): MCP tool call → bridge command → result. |
| [bridges/nvda/](bridges/nvda/) | The NVDA add-on (`nvdaMcpBridge`), built with scons. Its build copies `shared/`'s protocol module in, so bridge and server can never drift. |
| [specs/](specs/) | Numbered design specs (RFC-style). |

## Development

Requires [uv](https://docs.astral.sh/uv/). No NVDA checkout is needed for any
of it: the bridge's domain is pure Python and its NVDA edge is exempt from the
type check (see [AGENTS.md](AGENTS.md)).

```sh
# Shared wire contract
uv run --directory shared pytest
uv run --directory shared pyright

# Server (tests use a fake bridge)
uv run --directory mcpServer pytest
uv run --directory mcpServer pyright

# Bridge add-on: sync the shared wire module in, then headless tests + type check
py -3.13 bridges/nvda/sync_shared.py
uv run --directory bridges/nvda pytest
uv run --directory bridges/nvda pyright   # or: cd bridges/nvda && scons   to build the .nvda-addon
```

Wire the server into Claude Code from source:

```sh
claude mcp add --scope user nvda -- uv run --directory C:\projects\nvda-mcp\mcpServer nvda-mcp
```

## Status

[ROADMAP.md](ROADMAP.md) is the status board and the single source of truth
for what is done, in review, and next — kept current by each implementing PR.
The larger arcs (sessions A–F) are described in
[the spec's Milestones](specs/0001-agent-driven-nvda-over-mcp.md).

## License

GPL v2. See [LICENSE](LICENSE) / COPYING.txt. The bridge's spy synth driver is
adapted from NVDA's own GPL-2 system-test suite.
