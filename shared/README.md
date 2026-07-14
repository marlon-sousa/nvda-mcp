# nvda-mcp-wire

The **canonical, stdlib-only** JSON-lines wire protocol shared between the
nvda-mcp **server** (desktop CPython) and the nvda-mcp **bridge** (an NVDA
addon running on NVDA's embedded CPython).

Everything both hosts must agree on lives in `nvda_mcp_wire/protocol.py`:

- the message envelope (`Request` / `Response` / `ErrorInfo`),
- per-command param/result dataclasses,
- a small generic `from_dict` validator (walks `typing.get_type_hints`, raises
  `ValidationError` naming the offending field path),
- `to_dict` and JSON-lines `encode_message` / `decode_message` helpers,
- protocol version, default port, capture modes and command names.

**Why stdlib-only:** the addon build copies `protocol.py` straight into the
addon package, so the bridge carries no third-party dependency and cannot
collide with another addon's `sys.modules`. Because both sides run the exact
same bytes, the contract cannot drift. It is unit-tested once here, under
desktop Python.

```
uv run --directory shared pytest      # run the contract tests
uv run --directory shared pyright     # type-check (strict)
```
