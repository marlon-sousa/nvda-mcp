# Spec 0003 — bridge: Transcript port + the file transcript stack

Implementation contract for PR #7 (ROADMAP lane 1, entry 6; part of session B).
Like spec 0002, this PR was in flight when the spec-before-code process landed
(PR #8), so the spec is written retroactively and rides in the implementing
PR; the PR is judged against it like any other.

## Goal

Silent-mode runs are an audio blackout: nobody hears what NVDA "said", so the
transcript is how a tester reconstructs the run afterwards — gestures
interleaved with the speech they produced, plus session open/close and the
synth swap/restore. It is written bridge-side, so it is complete even if the
agent never fetched some speech, and its `path` is handed to the agent at
`hello`. The domain says **what** happened; how it is rendered and where it
lands are adapter business.

## Deliverables

All under `bridgeAddon/`; headless, no NVDA import anywhere in this PR. Every
module carries the mandatory ROLE header.

1. `domain/ports/transcript.py` — the **Transcript** port (`abc.ABC`): a
   `path` property (returned to the agent at `hello`), `open()`, and one
   method per session event in domain vocabulary — `session_opened(mode,
   synth)`, `synth_swapped(real_synth)`, `synth_restored(real_synth)`,
   `gesture(gesture_id)`, `speech(text)`, `note(text)`,
   `session_closed(reason)`.
2. `adapters/ports/file_writer.py` — the **FileWriter** seam (adapter seam,
   not a domain port — the domain has no idea the transcript is a file):
   `path`, `open()`, `write_line(text)`, `close()`. Two contract points are
   requirements, not tuning details: every line is flushed as written (a
   crashed
   harness must not lose the tail), and a failed write never raises (a broken
   log must never take a session down nor block the synth restore).
3. `adapters/file_transcript.py` — **FileTranscript**, the Transcript
   implementation and the upper layer of the pair: owns the transcript
   *vocabulary* (one timestamped line per event; `SESSION OPEN`, `SYNTH
   SWAP`, `GESTURE`, `SPEECH` with the text repr-quoted so whitespace
   survives, `NOTE`, `SYNTH RESTORE`, `SESSION CLOSE`). Timestamps come from
   an injectable callable defaulting to wall clock, so tests are
   deterministic. Events outside an open session are dropped, not buffered.
   Also `create_session_log(logs_dir, keep=20, ...)` — the composition helper
   that picks the concrete `TextFileWriter`, opens a fresh
   `session-<stamp>.log` (name stamp time-sortable, so lexical sort is
   chronological), and prunes older `session-*.log` files beyond `keep`,
   leaving unrelated files alone.
4. `adapters/text_file_writer.py` — **TextFileWriter**, the FileWriter leaf:
   UTF-8, line-buffered real file IO, swallowing `OSError` per the seam
   contract. Deliberately decision-free — and deliberately NOT NVDA's
   `logHandler`, which is a single global diagnostics log gated by the user's
   level, not a private per-session artifact.
5. `tests/fakes/file_writer.py` — **FakeFileWriter** subclassing the seam:
   records lines in memory so the vocabulary is asserted exactly.
6. `tests/unit/adapters/test_file_transcript.py` — vocabulary tests against
   the fake (fixture-based: every test wants the same writer/transcript pair,
   and the fixture makes the shared-writer relationship structural), plus
   `create_session_log` tests against a real `tmp_path` (it is the one piece
   that touches the disk: path reporting, pruning, sparing unrelated files).

## Acceptance criteria

Automated, on the `bridge` CI job (plus `shared`, `server`, and the checklist
gate staying green):

1. Every event produces its exact timestamped line, in order.
2. Speech text is quoted so leading/trailing whitespace survives reading.
3. `open`/`session_closed` delegate open/close to the writer.
4. `path` is the writer's path.
5. Events before `open()` and after `session_closed()` are dropped.
6. `create_session_log` writes a real file, reports the real path, prunes
   oldest sessions beyond `keep`, and never deletes non-`session-*.log`
   files.
7. The leaf (`text_file_writer.py`) and the two port files have no test
   files — the deliberate-omission table in AGENTS.md applies.
8. pyright strict is clean; nothing here needs the ignore list.

No manual NVDA checklist: this PR has no NVDA-facing surface. (The
transcript's first live use arrives with session C's wiring.)

## Out of scope

- Wiring the transcript into a real session (`create_session_log`'s
  production caller) — session C.
- The Session controller reporting events through the port — the next lane-1
  entry (session controller).
- Transcript rotation policy beyond count-based pruning.

## Definition of done

Merged with green CI; ROADMAP entry 6 flipped to Done by this PR; any
amendment this spec needs during review rides in this same PR.
