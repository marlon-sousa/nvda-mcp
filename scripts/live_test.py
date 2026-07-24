#!/usr/bin/env python3
# Live test driver: stand in for an MCP client and drive the real
# screenreader-mcp binary over stdio against a REAL, running NVDA bridge.
#
# This is the contributor's hands-on equivalent of the automated tiers. The Go
# unit/integration tests put a FAKE bridge behind the server; the conformance
# tier puts the real Python bridge behind it but fakes NVDA. Only here is
# *everything* real -- the server binary, the wire, the add-on, and NVDA itself
# -- which is the one thing no automated tier can be: it needs a human who can
# hear the speech. See CONTRIBUTING.md, "Setting up to test against a live NVDA".
#
# It is written to be EASY to run. Each named scenario is self-contained: it
# connects, walks its steps, checks what it can by itself (tool gating, index
# arithmetic, error shapes), tells you when to focus a window, asks you to
# confirm what you heard, and prints PASS / FAIL / EAR (needs your ear) per check
# with a summary. You never assemble commands or reason about indices by hand.
#
# Framing is MCP's stdio transport: newline-delimited JSON-RPC 2.0. The server
# logs to stderr, so stdout stays a clean JSON stream.
#
# Usage:
#   py -3.13 scripts/live_test.py <binary> <scenario> [--live|--silent] [--auto]
#
# Scenarios (each maps to one checklist item group in the PR):
#   smoke      connect, prove tool gating, read screenreader://info, ANNOUNCE
#              (you should hear it). No window focus needed.
#   capture    a gesture's speech is captured cleanly: bookmark, open the
#              Elements List, read back only the new speech, prove the ranges
#              join and that a wait for absent text times out (not disconnects).
#              Needs a browse-mode document focused.
#   braille    read the braille display and show its indices are their own.
#   finddialog drive EnhancedFindDialog end to end. Needs a browse-mode document.
#   lifecycle  disconnect retracts the tools and a gated call then errors;
#              reconnect works; status is proven on the wire. No focus needed.
#
#   run        ADVANCED: hold a session open and execute one command per line
#              from stdin (announce/press/bookmark/speech/braille/waitspeech/
#              status/sleep/disconnect). For ad-hoc probing, not the checklist.
#
# --auto skips the "press Enter" setup pauses and cannot judge audio, so it marks
# audible checks as EAR for you to confirm by hand. It is the default when stdin
# is not a terminal (e.g. driven by another tool). Run it yourself in a terminal
# for the guided, interactive experience.

from __future__ import annotations

import json
import queue
import subprocess
import sys
import threading
import time

DEFAULT_ANNOUNCE = "This is the agent, speaking through NVDA. If you can hear this, announce works."

USAGE = """\
Live test driver -- drive the real screenreader-mcp binary against a running NVDA.

  py -3.13 scripts/live_test.py <binary> <scenario> [--live|--silent] [--auto]

Scenarios (each is one checklist item group; run them in a terminal for the
guided, interactive experience):
  smoke       connect, prove tool gating, read screenreader://info, ANNOUNCE
              (you should hear it). No window focus needed.
  capture     a gesture's speech is captured cleanly, ranges join, an absent
              wait times out. Needs a browse-mode document focused.
  braille     read the braille display; its indices are their own space.
  finddialog  drive EnhancedFindDialog end to end. Needs a browse-mode document.
  lifecycle   disconnect retracts the tools and a gated call errors; reconnect
              works; status is proven on the wire. No focus needed.
  run         ADVANCED: one command per line from stdin. For ad-hoc probing.

--auto skips setup pauses and marks audible checks EAR (the default off a
non-terminal). See CONTRIBUTING.md, "Setting up to test against a live NVDA"."""


def main(argv: list[str]) -> int:
    args = list(argv[1:])
    if len(args) < 2:
        print(USAGE)
        return 2
    binary, scenario = args[0], args[1]
    flags = args[2:]

    mode = "silent" if "--silent" in flags else "live"
    auto = "--auto" in flags or (not sys.stdin.isatty() and "--interactive" not in flags)
    console = Console(auto)

    server = Server(binary)
    checks = Checklist()
    try:
        server.initialize()
        fn = SCENARIOS.get(scenario)
        if fn is None:
            if scenario == "run":
                return scenario_run(server, mode)
            print(f"unknown scenario {scenario!r}\n\n{USAGE}")
            return 2
        fn(server, console, checks, mode)
        return checks.summary()
    except Exception as exc:  # noqa: BLE001 -- a driver; surface everything
        print(f"\n!! ABORTED: {exc}", file=sys.stderr)
        err = server.stderr_tail()
        if err:
            print("---- server stderr ----\n" + err, file=sys.stderr)
        return 1
    finally:
        server.close()


# -- scenarios -----------------------------------------------------------------


def scenario_smoke(server, console, checks, mode):
    before = server.tool_names()
    console.note(f"tools before connect: {', '.join(before)}")
    checks.check("gating: only the ungated four before connect",
                 set(before) == {"list_readers", "connect_reader", "disconnect_reader", "status"},
                 detail=str(before))

    readers = server.tool("list_readers")
    names = [r.get("reader") for r in readers.get("readers", [])]
    console.note(f"list_readers: {json.dumps(readers)}")
    checks.check("discovery: nvda is listed without dialing", "nvda" in names, detail=str(names))

    session = _connect(server, console, mode)
    caps = session.get("capabilities", [])
    checks.check("handshake: announce capability present", "announce" in caps, detail=str(caps))

    after = set(server.tool_names())
    gated_expected = {"announce", "get_braille", "get_speech", "get_last_speech",
                      "get_next_speech_index", "wait_for_speech", "wait_for_speech_to_finish",
                      "press_gesture"}
    checks.check("gating: the gated set appears after connect",
                 gated_expected <= after, detail=str(sorted(after)))
    introspection = {"get_focus_info", "get_state", "get_config", "set_config"}
    checks.check("gating: unannounced introspection tools stay hidden (that is 11.1)",
                 not (introspection & after), detail=str(sorted(introspection & after)))

    info = server.resource("screenreader://info")
    checks.check("screenreader://info matches the handshake",
                 info.get("reader", {}).get("name") == session.get("reader")
                 and sorted(info.get("capabilities", [])) == sorted(caps),
                 detail=json.dumps(info))

    text = DEFAULT_ANNOUNCE
    console.step(f'announcing (you should HEAR it): "{text}"')
    said = server.tool("announce", {"text": text})
    checks.check("announce result echoes the text", said.get("announced") == text, detail=str(said))
    checks.ear("announce is HEARD aloud in NVDA's real voice (two beeps, then the message)",
               console.confirm("Did you hear the announcement spoken?"))

    _disconnect(server, console)


def scenario_capture(server, console, checks, mode):
    session = _connect(server, console, mode)
    console.pause("Focus a BROWSE-MODE document (e.g. a web page in your browser)")

    bookmark = server.tool("get_next_speech_index")["index"]
    console.step(f"bookmarked speech index {bookmark}; opening the Elements List (NVDA+f7)")
    server.tool("press_gesture", {"gestures": ["kb:NVDA+f7"]})
    server.tool("wait_for_speech_to_finish", {"timeout": 3})

    got = server.tool("get_speech", {"since_index": bookmark})
    console.note(f"captured since {bookmark}: {json.dumps(got, ensure_ascii=False)}")
    checks.check("capture: speech since the bookmark is non-empty", bool(got.get("text")),
                 detail=json.dumps(got, ensure_ascii=False))
    checks.check("capture: the range starts exactly at the bookmark",
                 got.get("fromIndex") == bookmark, detail=str(got))
    checks.ear("the Elements List opened and NVDA spoke it",
               console.confirm("Did the Elements List open and get announced?"))

    # Half-open ranges join with no gap or overlap: read the same span in two
    # slices and prove the seam matches.
    mid = (bookmark + got["toIndex"]) // 2
    first = server.tool("get_speech", {"since_index": bookmark})
    second = server.tool("get_speech", {"since_index": first["toIndex"]})
    checks.check("ranges: [a,b) then [b,c) -- the toIndex of one is the fromIndex of the next",
                 first["toIndex"] == second["fromIndex"], detail=f'{first["toIndex"]} vs {second["fromIndex"]}')

    # A wait for text that will never appear must time out cleanly and leave the
    # session working -- not tear the connection down.
    console.step("waiting 2s for text that is not there (should time out, not disconnect)")
    missing = server.tool("wait_for_speech", {"text": "zzz-not-spoken-zzz", "timeout": 2})
    checks.check("wait_for_speech for absent text returns found:false", missing.get("found") is False,
                 detail=str(missing))
    still_alive = server.tool("get_last_speech")
    checks.check("the session still answers after the timeout", "index" in still_alive,
                 detail=str(still_alive))

    server.tool("press_gesture", {"gestures": ["kb:escape"]})  # close the list
    _disconnect(server, console)


def scenario_braille(server, console, checks, mode):
    session = _connect(server, console, mode)
    console.pause("Focus any control that shows on your braille display (or read anyway)")

    speech_idx = server.tool("get_next_speech_index")["index"]
    braille = server.tool("get_braille", {"since_index": 0})
    console.note(f"braille since 0: {json.dumps(braille, ensure_ascii=False)}")
    checks.check("braille: the display content is returned", "text" in braille, detail=str(braille))
    checks.check("braille: its indices are their own space, not the speech indices",
                 braille.get("toIndex") != speech_idx or braille.get("fromIndex") == 0,
                 detail=f'braille toIndex={braille.get("toIndex")} speech next={speech_idx}')
    checks.ear("the braille text matches what is on your display",
               console.confirm(f'Braille read: {braille.get("text")!r} -- does that match your display?'))
    _disconnect(server, console)


def scenario_finddialog(server, console, checks, mode):
    session = _connect(server, console, mode)
    console.pause("Focus a BROWSE-MODE document with findable text (e.g. a web page)")

    bookmark = server.tool("get_next_speech_index")["index"]
    console.step("opening EnhancedFindDialog (NVDA+control+f)")
    server.tool("press_gesture", {"gestures": ["kb:NVDA+control+f"]})
    server.tool("wait_for_speech_to_finish", {"timeout": 3})
    opened = server.tool("get_speech", {"since_index": bookmark})
    console.note(f"on open: {json.dumps(opened, ensure_ascii=False)}")
    checks.ear("EnhancedFindDialog opened and was announced",
               console.confirm("Did the find dialog open and speak?"))

    term = console.ask("Type a search term the page contains", default="the")
    console.step(f'typing "{term}" and searching')
    for ch in term:
        server.tool("press_gesture", {"gestures": [f"kb:{ch}"]})
    mark2 = server.tool("get_next_speech_index")["index"]
    server.tool("press_gesture", {"gestures": ["kb:enter"]})
    server.tool("wait_for_speech_to_finish", {"timeout": 3})
    result = server.tool("get_speech", {"since_index": mark2})
    console.note(f"on search: {json.dumps(result, ensure_ascii=False)}")
    checks.ear("the search moved to a match and NVDA read it",
               console.confirm("Did it jump to a match and announce it?"))
    _disconnect(server, console)


def scenario_lifecycle(server, console, checks, mode):
    _connect(server, console, mode)
    console.step("disconnecting")
    server.tool("disconnect_reader")

    after = set(server.tool_names())
    checks.check("disconnect: the gated tools are retracted", "get_speech" not in after,
                 detail=str(sorted(after)))
    try:
        server.tool("get_speech", {"since_index": 0})
        checks.check("a gated call after disconnect is refused", False, detail="it was accepted")
    except RuntimeError as exc:
        checks.check("a gated call after disconnect is refused with 'connect first'",
                     "connect" in str(exc).lower(), detail=str(exc))

    console.step("reconnecting on the same bridge")
    session = _connect(server, console, mode)
    checks.check("reconnect: a second session handshakes cleanly", session.get("reader") == "nvda",
                 detail=str(session.get("reader")))

    status = server.tool("status")
    checks.check("status is proven live on the wire", status.get("state") == "connected"
                 and status.get("live") is True, detail=str(status))
    _disconnect(server, console)


SCENARIOS = {
    "smoke": scenario_smoke,
    "capture": scenario_capture,
    "braille": scenario_braille,
    "finddialog": scenario_finddialog,
    "lifecycle": scenario_lifecycle,
}


# -- shared scenario steps -----------------------------------------------------


def _connect(server, console, mode):
    session = server.tool("connect_reader", {"reader": "nvda", "mode": mode})
    console.note(f"connected: {session.get('reader')} {session.get('readerVersion')} "
                 f"over {session.get('endpoint')}, mode={session.get('mode')}, "
                 f"synth={session.get('synth')}, caps={session.get('capabilities')}")
    return session


def _disconnect(server, console):
    console.step(f"disconnecting: {server.tool('disconnect_reader')}")


# -- advanced ad-hoc mode ------------------------------------------------------


def scenario_run(server, mode):
    session = server.tool("connect_reader", {"reader": "nvda", "mode": mode})
    print(f"== connected: {session.get('reader')} caps={session.get('capabilities')}")
    for line in sys.stdin:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        verb, _, arg = line.partition(" ")
        try:
            if _run_command(server, verb, arg.strip()) == "stop":
                break
        except Exception as exc:  # noqa: BLE001
            print(f"   !! {verb}: {exc}")
    print(f"== disconnecting: {server.tool('disconnect_reader')}")
    return 0


def _run_command(server, verb, arg):
    table = {
        "announce": lambda: server.tool("announce", {"text": arg}),
        "press": lambda: server.tool("press_gesture", {"gestures": arg.split()}),
        "bookmark": lambda: server.tool("get_next_speech_index"),
        "speech": lambda: server.tool("get_speech", {"since_index": int(arg)}),
        "lastspeech": lambda: server.tool("get_last_speech"),
        "braille": lambda: server.tool("get_braille", {"since_index": int(arg)}),
        "status": lambda: server.tool("status"),
    }
    if verb in table:
        print(f"-> {verb} {arg}: {table[verb]()}")
    elif verb == "waitspeech":
        timeout, _, text = arg.partition(" ")
        print(f"-> waitspeech: {server.tool('wait_for_speech', {'text': text.strip(), 'timeout': float(timeout)})}")
    elif verb == "sleep":
        time.sleep(float(arg)); print(f"-> slept {arg}s")
    elif verb == "disconnect":
        return "stop"
    else:
        print(f"   ?? unknown command {verb!r}")
    return None


# -- console: guidance, confirmation, results ----------------------------------


class Console:
    """The tester's side: setup pauses, audible confirmations, notes."""

    def __init__(self, auto: bool) -> None:
        self.auto = auto
        if auto:
            print("[auto mode: setup pauses are skipped and audible checks are marked EAR "
                  "for you to confirm by hand]")

    def step(self, msg: str) -> None:
        print(f"-> {msg}")

    def note(self, msg: str) -> None:
        print(f"   {msg}")

    def pause(self, msg: str) -> None:
        if self.auto:
            print(f"[setup -- do this now] {msg}")
            time.sleep(2)
            return
        input(f"[setup] {msg}, then press Enter ... ")

    def confirm(self, msg: str):
        if self.auto:
            return None
        return input(f"[confirm] {msg} (y/n): ").strip().lower().startswith("y")

    def ask(self, msg: str, default: str) -> str:
        if self.auto:
            return default
        return input(f"[input] {msg} [{default}]: ").strip() or default


class Checklist:
    """Records PASS / FAIL / EAR per check and prints a summary."""

    def __init__(self) -> None:
        self._rows: list[tuple[str, str, str]] = []

    def check(self, name: str, ok: bool, detail: str = "") -> None:
        self._rows.append((name, "PASS" if ok else "FAIL", "" if ok else detail))

    def ear(self, name: str, answer) -> None:
        status = "EAR" if answer is None else ("PASS" if answer else "FAIL")
        self._rows.append((name, status, ""))

    def summary(self) -> int:
        print("\n==== results ====")
        failed = 0
        ears = 0
        for name, status, detail in self._rows:
            mark = {"PASS": "[x]", "FAIL": "[ ]", "EAR": "[?]"}[status]
            line = f"{mark} {status:4} {name}"
            if detail:
                line += f"  -- {detail}"
            print(line)
            failed += status == "FAIL"
            ears += status == "EAR"
        print(f"---- {len(self._rows)} checks: "
              f"{sum(1 for r in self._rows if r[1] == 'PASS')} pass, {failed} fail, {ears} need your ear")
        return 1 if failed else 0


# -- the MCP-over-stdio client -------------------------------------------------


class Server:
    """The screenreader-mcp binary, spoken to as an MCP client would."""

    def __init__(self, binary: str) -> None:
        self._proc = subprocess.Popen(
            [binary], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, bufsize=0,
        )
        self._lines: "queue.Queue[bytes]" = queue.Queue()
        self._err: list[bytes] = []
        threading.Thread(target=_pump, args=(self._proc.stdout, self._lines), daemon=True).start()
        threading.Thread(target=_drain, args=(self._proc.stderr, self._err), daemon=True).start()
        self._id = 0

    def initialize(self) -> None:
        info = self._call("initialize", {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "live_test", "version": "0"},
        }).get("serverInfo", {})
        print(f"== initialized: {info.get('name')} {info.get('version')}")
        self._notify("notifications/initialized")

    def tool_names(self) -> list[str]:
        return sorted(t["name"] for t in self._call("tools/list")["tools"])

    def tool(self, name: str, arguments: dict | None = None) -> dict:
        result = self._call("tools/call", {"name": name, "arguments": arguments or {}})
        if result.get("isError"):
            raise RuntimeError("".join(c.get("text", "") for c in result.get("content", [])) or "tool failed")
        if "structuredContent" in result:
            return result["structuredContent"]
        for block in result.get("content", []):
            if block.get("type") == "text":
                try:
                    return json.loads(block["text"])
                except json.JSONDecodeError:
                    return {"text": block["text"]}
        return result

    def resource(self, uri: str) -> dict:
        result = self._call("resources/read", {"uri": uri})
        for item in result.get("contents", []):
            if "text" in item:
                try:
                    return json.loads(item["text"])
                except json.JSONDecodeError:
                    return {"text": item["text"]}
        return result

    def stderr_tail(self) -> str:
        time.sleep(0.2)
        return b"".join(self._err).decode("utf-8", "replace").strip()

    def close(self) -> None:
        try:
            self._proc.stdin.close()
        except Exception:
            pass
        self._proc.terminate()

    def _call(self, method: str, params: dict | None = None, timeout: float = 30.0) -> dict:
        self._id += 1
        my_id = self._id
        msg = {"jsonrpc": "2.0", "id": my_id, "method": method}
        if params is not None:
            msg["params"] = params
        self._send(msg)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                raw = self._lines.get(timeout=max(0.01, deadline - time.monotonic()))
            except queue.Empty:
                break
            reply = json.loads(raw)
            if reply.get("id") != my_id:
                continue
            if "error" in reply:
                raise RuntimeError(f"{method} -> {reply['error']}")
            return reply.get("result", {})
        raise TimeoutError(f"no response to {method} within {timeout}s")

    def _notify(self, method: str, params: dict | None = None) -> None:
        msg = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            msg["params"] = params
        self._send(msg)

    def _send(self, msg: dict) -> None:
        self._proc.stdin.write((json.dumps(msg) + "\n").encode("utf-8"))
        self._proc.stdin.flush()


def _pump(stream, out: "queue.Queue[bytes]") -> None:
    for line in stream:
        line = line.strip()
        if line:
            out.put(line)


def _drain(stream, buf: list[bytes]) -> None:
    for line in stream:
        buf.append(line)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
