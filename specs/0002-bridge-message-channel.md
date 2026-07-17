# Spec 0002 — bridge: MessageChannel port + JSON-lines adapter

Implementation contract for PR #6 (ROADMAP lane 1, entry 5; part of session B).
This PR was in flight when the spec-before-code process landed (PR #8), so the
spec is written retroactively and rides in the implementing PR itself; the PR
is judged against it like any other.

## Goal

Give the Session controller its single I/O collaborator: a domain port that
deals in **whole protocol messages**, with every byte-level concern — framing,
JSON encode/decode, the socket — behind it in layered adapters. This is what
lets session logic be tested by scripting messages, never bytes, and shrinks
the untestable code to a leaf that arrives in session C.

## Deliverables

All under `bridgeAddon/`; headless, no NVDA import anywhere in this PR. Every
module carries the mandatory ROLE header.

1. `domain/ports/message_channel.py` — the **MessageChannel** port
   (`abc.ABC`): `read_message() -> dict | Timeout`, `write(message)`,
   `close()`. Its signalling types live in the same file, per the
   one-file-per-port rule:
   - `ChannelClosed` — raised at EOF; the Session catches it to end the
     session.
   - `Timeout` / the `TIMEOUT` sentinel — "no message within the poll
     window", distinct from `None` (a valid JSON value) and from
     `ChannelClosed`; it is what lets the Session periodically regain control
     to check heartbeat and inactivity deadlines. A class rather than a bare
     object so `dict | Timeout` narrows under strict pyright.
   - An unreadable line surfaces as `protocol.ValidationError` from
     `read_message` — the Session reports it and carries on; garbage bytes
     must not kill a session.
2. `adapters/ports/transport.py` — the **Transport** seam (an adapter seam,
   not a domain port — the domain never sees bytes): `recv() -> bytes`
   returning `b""` at EOF and raising `TimeoutError` when idle, `sendall`,
   `close`. The contract deliberately mirrors a real socket with
   `settimeout`, so the session-C leaf implementation is almost nothing.
3. `adapters/json_lines_channel.py` — **JsonLinesChannel**, the MessageChannel
   implementation over a Transport. Owns framing (a private `_LineReader`
   reassembles chunks into newline-delimited frames) and JSON encode/decode
   via the synced `protocol` module. Invariant: buffered complete lines drain
   before the transport is polled again, so a message that already arrived is
   never lost to a later timeout.
4. `tests/fakes/script.py` — shared scaffolding for replay fakes
   (`ScriptedQueue`, `TIMEOUT_EVENT`, `CLOSED_EVENT`): the three ideas every
   read-side fake needs (a scripted event, "peer stayed quiet", "peer went
   away") defined once, whether the fake replays bytes (FakeTransport) or
   whole messages (the Session's future FakeChannel).
5. `tests/fakes/transport.py` — **FakeTransport** subclassing the Transport
   seam: replays scripted bytes / timeouts / EOF, records everything written,
   and decodes it back via `responses()`.
6. `tests/unit/adapters/test_json_lines_channel.py` — the **only** test module
   in which bytes appear: framing is this adapter's job, proven here once.
   Uses a builder helper, not a fixture, because every test scripts a
   different byte stream (per AGENTS.md fixture policy).

## Acceptance criteria

Automated, on the `bridge` CI job (plus `shared`, `server`, and the checklist
gate staying green):

1. A whole message in one chunk is read and decoded.
2. A message split across chunks is reassembled.
3. Two messages in one chunk are delivered separately, the second from the
   buffer without touching the transport again.
4. A buffered message is never lost to a later timeout.
5. A quiet poll returns the `TIMEOUT` sentinel, and reading continues to work
   after a timeout.
6. EOF raises `ChannelClosed`.
7. A non-JSON line raises `protocol.ValidationError`.
8. `write` encodes a wire dataclass as exactly one newline-terminated frame.
9. `close` closes the underlying transport.
10. pyright strict is clean; the new files need no entry in the ignore list
    (nothing here imports NVDA).

No manual NVDA checklist: this PR has no NVDA-facing surface.

## Out of scope

- The real socket leaf (`adapters/socket_transport.py`) and the accept loop —
  session C, where the Transport seam gets its production implementation.
- The Session controller that consumes the port — the next lane-1 entry.
- Any change to the wire protocol itself.

## Definition of done

Merged with green CI; ROADMAP entry 5 flipped to Done by this PR; any
amendment this spec needs during review rides in this same PR.
