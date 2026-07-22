# screenreader-mcp

The MCP server half of this repo: an MCP client speaks MCP over stdio to this
binary, and this binary speaks JSON lines to **one screen-reader bridge** over a
local endpoint — a Windows named pipe or loopback TCP.

It is a **reader-agnostic chassis** ([spec 0005](../specs/0005-multi-reader-direction.md),
[0013](../specs/0013-mcp-server.md)): it contains no NVDA knowledge and no
`if reader == …`. Which reader answered, and what it can do, come from the
`hello` handshake.

**Status: entry 10a.** The module, the generated wire binding, the layered
endpoint configuration and the bridge client are in place — it dials a bridge
and completes a handshake. The MCP surface itself arrives in 10b, so running the
binary today reports that and exits.

## Build and run

```sh
go -C server build -o screenreader-mcp.exe ./cmd/screenreader-mcp
```

Statically linked (`CGO_ENABLED=0`, no cgo dependencies), so the artifact is one
file that runs with no runtime installed.

| Flag | Meaning |
|---|---|
| `--reader name=spec` | Repeatable, highest precedence. One endpoint for a reader, e.g. `nvda=pipe:nvdaMcpBridge` or `talkback=tcp:127.0.0.1:9010`. Repeating a name adds an endpoint to that reader, in order. |
| `--config <path>` | A JSON file replacing or extending the embedded defaults, per reader. |
| `--print-default-config` | Print the embedded defaults and exit — redirect it to a file and edit it. |
| `--version` | Print the version and exit. |
| `--verbose` | Log debug detail to stderr. |

There is deliberately no `--capture-mode` and no `--reader-log-level`: the wire
contract fixes both at `hello` for the session's lifetime, so they are
`connect_reader` parameters chosen by the agent that knows what the session is
for.

## The shipped endpoints

No arguments are needed, because the binary ships knowing where our bridges
listen. This is `config/defaults.json`, embedded with `go:embed` and reproduced
here:

```json
{
  "readers": [
    {
      "name": "nvda",
      "endpoints": [
        "pipe:nvdaMcpBridge",
        "tcp:127.0.0.1:8765"
      ]
    }
  ]
}
```

Two endpoints per reader is not redundancy: the NVDA bridge's control dialog
lets the user switch between named pipe and loopback TCP, so `connect_reader`
takes a **reader**, tries that reader's endpoints in declared order, and reports
which one answered.

A listening pipe that belongs to no configured reader is never reported and
cannot be connected to — the reader set is known before the process starts, and
nothing is invented at runtime.

## Layout

Ports and adapters, the same four roles as the NVDA bridge (see
[AGENTS.md](../AGENTS.md)):

```
server/
  domain/         # PURE core: no wire types, no MCP SDK, no sockets
    ports/        #   one interface per file
    entities/     #   the pure model
  adapters/       # the only place the OS, the SDK and the wire binding live
    wire/         #   GENERATED from specs/wire/v1/schema.json; do not edit
    bridge/       #   the JSON-lines client, the handshake, the transport leaves
    discovery/    #   the pipe scan
    ports/        #   seams BETWEEN adapters (the domain never sees these)
  config/         # the embedded defaults and their layered loader
  wiring/         # the composition root: read it top to bottom
  cmd/            # the entry point
  tools/wiregen/  # the wire binding generator (a dev tool, not shipped)
  fakes/          # one hand-written fake per port
  testsupport/    # builders and the fake bridge
  tests/          # architecture gate; integration tiers behind build tags
```

## Development

```sh
go -C server build ./...
go -C server test ./...                      # unit tests
go -C server test -tags integration ./...    # real transports, fake bridge
go -C server vet ./...
go -C server generate ./adapters/wire        # regenerate the wire binding
```

The wire binding is generated and committed, and CI regenerates and diffs it, so
it can never drift from the published contract. What the two halves of this repo
share is [that contract](../specs/wire/v1/) — a JSON Schema and a prose
document — not code: each side binds it in its own language, and 10c's
conformance job proves they agree.
