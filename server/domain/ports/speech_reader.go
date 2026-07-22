// screenreader-mcp domain -- the SpeechReader port (the `speech` capability).
// Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
//
// ROLE: domain port. One capability GROUP, not one command -- protocol.md §4
// groups these five commands under `speech`, and the port set mirrors the
// capability set exactly so a missing capability is a missing collaborator.
// IMPLEMENTED BY: adapters/bridge/json_lines_client.go.
// USED BY: 10b's speech tool controllers, one controller per tool.
// HANDED OUT BY: the handshake, which sets this port on the ReaderConnection
// only when the reader announced `speech` -- so a reader without it produces a
// nil collaborator rather than a runtime check.
//
// Its DTOs live in this file, per AGENTS.md: a port's own types belong with the
// port. They are domain vocabulary; adapters/bridge maps them to and from the
// generated wire structs.
package ports

import "time"

// SpeechRange is a half-open window of captured speech: [FromIndex, ToIndex).
// ToIndex is exactly the sinceIndex to pass next, with no overlap and no gap
// (protocol.md §7).
type SpeechRange struct {
	Text      string
	FromIndex int
	ToIndex   int
}

// LastSpeech is the most recent captured utterance and the index it occupies.
type LastSpeech struct {
	Text  string
	Index int
}

// SpeechWait asks the reader to block until matching speech appears.
type SpeechWait struct {
	// Text is what to wait for.
	Text string

	// AfterIndex restricts the match to items at or after that index. Nil
	// means "anywhere in what has been captured", which is a different
	// question from "at or after 0" only in intent -- but the wire
	// distinguishes them, so the domain does too.
	AfterIndex *int

	// Timeout is how long to wait. Zero means the bridge's own default.
	Timeout time.Duration
}

// SpeechMatch is the outcome of a wait. Found says whether the text appeared;
// Index and Text describe the match when it did.
type SpeechMatch struct {
	Found bool
	Index int
	Text  string
}

// SpeechReader is everything the `speech` capability can be asked.
type SpeechReader interface {
	// SpeechSince returns captured speech from sinceIndex onward.
	SpeechSince(sinceIndex int) (SpeechRange, error)

	// LastSpeech returns the most recent utterance.
	LastSpeech() (LastSpeech, error)

	// NextSpeechIndex returns the index the next captured item will take, so
	// a caller can note "now", act, and then read only what its action
	// produced.
	NextSpeechIndex() (int, error)

	// WaitForSpeech blocks until the text appears or the timeout elapses.
	WaitForSpeech(wait SpeechWait) (SpeechMatch, error)

	// WaitForSpeechToFinish blocks until speech settles or the timeout
	// elapses; the bool reports which. A zero timeout means the bridge's own
	// default.
	WaitForSpeechToFinish(timeout time.Duration) (bool, error)
}
