# ${addon_summary} ${addon_version}

A bridge that lets an AI agent **drive NVDA** (via the **nvda-mcp** server):
send keyboard gestures, read back what NVDA would speak and braille, and
introspect its state. The first use is **functional testing of NVDA add-ons** —
replacing manual testing — but the same primitives support a wider range of
agent-driven NVDA workflows.

The add-on is **inert until a session connects**. While idle it never swaps
your synthesizer and installs no hooks with side effects, so it is safe to
leave permanently installed.

- Minimum NVDA version: ${addon_minimumNVDAVersion}
- Last tested NVDA version: ${addon_lastTestedNVDAVersion}
- Source and issues: ${addon_url}

## How it works

This add-on is only half of the system. It opens a loopback-only TCP server and
speaks a small JSON-lines protocol. The other half — the **nvda-mcp server** —
is a separate program that your AI agent's MCP client launches; it connects to
this add-on and exposes NVDA to the agent as MCP tools.

The two are versioned together: the handshake rejects a mismatched
bridge/server pair with a clear error, so always install the server build that
pairs with this add-on version.

## Setup

1. Install this add-on (you have already done this if you are reading it from
   the Add-on Store).
2. Download the matching server build:
   ${addon_url}/releases/download/${addon_version}/nvda-mcp-server-${addon_version}.zip
3. Extract it, then register it with your MCP client. For Claude Code:

   ```
   claude mcp add nvda -- <extracted>\nvda-mcp-server.exe
   ```

An agent-oriented setup file (`mcp-setup.md`) ships alongside this document with
the exact download URL, `claude mcp add` command, and a ready-to-paste
`.mcp.json` snippet, so an agent pointed at this add-on can configure itself.

## Safety

- The bridge binds to `127.0.0.1` only.
- In **silent** capture mode it swaps in a bundled spy synthesizer for the
  duration of a session. Restoration of your real synthesizer is guaranteed on
  every teardown path (disconnect, error, timeout, add-on unload), plus a panic
  gesture and a config-save guard — a crashed harness must never leave you with
  a mute screen reader.
- Because the bridge can inject keystrokes, treat it as a development tool.

## License

${addon_license}. See COPYING.txt. The bundled spy synthesizer is adapted from
NVDA's own GPL-2 system-test suite.
