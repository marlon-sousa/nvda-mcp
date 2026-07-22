// screenreader-mcp fakes -- FakeSpeechReader: the SpeechReader port double.
// Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
//
// ROLE: test double. MIRRORS domain/ports/speech_reader.go.
// USED BY: 10b's speech tool controller tests.
//
// Stateful rather than call-scripted: it keeps an append-only log of utterances
// and answers from it, so index arithmetic -- the half-open [from, to) window
// that makes ToIndex the next sinceIndex -- is exercised for real rather than
// hand-fed per test.
package fakes

import (
	"strings"
	"sync"
	"time"

	"github.com/marlon-sousa/screen-readers-mcp/server/domain/ports"
)

// FakeSpeechReader is an in-memory speech log.
type FakeSpeechReader struct {
	mu        sync.Mutex
	spoken    []string
	err       error
	finished  bool
	waitCalls []ports.SpeechWait
}

var _ ports.SpeechReader = (*FakeSpeechReader)(nil)

// NewFakeSpeechReader builds an empty log that reports speech as settled.
func NewFakeSpeechReader() *FakeSpeechReader { return &FakeSpeechReader{finished: true} }

// Speak appends an utterance, as the reader would have.
func (f *FakeSpeechReader) Speak(text ...string) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.spoken = append(f.spoken, text...)
}

// FailWith makes every call return err, for the paths where a live bridge
// refuses.
func (f *FakeSpeechReader) FailWith(err error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.err = err
}

// SetFinished controls what WaitForSpeechToFinish reports.
func (f *FakeSpeechReader) SetFinished(finished bool) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.finished = finished
}

// Waits records every wait that was asked for -- a spy, used only where the
// interaction IS the requirement (that a tool passed the caller's afterIndex
// through, say).
func (f *FakeSpeechReader) Waits() []ports.SpeechWait {
	f.mu.Lock()
	defer f.mu.Unlock()
	return append([]ports.SpeechWait(nil), f.waitCalls...)
}

func (f *FakeSpeechReader) SpeechSince(sinceIndex int) (ports.SpeechRange, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	if f.err != nil {
		return ports.SpeechRange{}, f.err
	}
	if sinceIndex < 0 {
		sinceIndex = 0
	}
	if sinceIndex > len(f.spoken) {
		sinceIndex = len(f.spoken)
	}
	return ports.SpeechRange{
		Text:      strings.Join(f.spoken[sinceIndex:], "\n"),
		FromIndex: sinceIndex,
		ToIndex:   len(f.spoken),
	}, nil
}

func (f *FakeSpeechReader) LastSpeech() (ports.LastSpeech, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	if f.err != nil {
		return ports.LastSpeech{}, f.err
	}
	if len(f.spoken) == 0 {
		return ports.LastSpeech{Index: 0}, nil
	}
	return ports.LastSpeech{Text: f.spoken[len(f.spoken)-1], Index: len(f.spoken) - 1}, nil
}

func (f *FakeSpeechReader) NextSpeechIndex() (int, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	if f.err != nil {
		return 0, f.err
	}
	return len(f.spoken), nil
}

func (f *FakeSpeechReader) WaitForSpeech(wait ports.SpeechWait) (ports.SpeechMatch, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.waitCalls = append(f.waitCalls, wait)
	if f.err != nil {
		return ports.SpeechMatch{}, f.err
	}
	from := 0
	if wait.AfterIndex != nil {
		from = *wait.AfterIndex
	}
	for i := from; i < len(f.spoken); i++ {
		if strings.Contains(f.spoken[i], wait.Text) {
			return ports.SpeechMatch{Found: true, Index: i, Text: f.spoken[i]}, nil
		}
	}
	// Not found is an ANSWER, not an error: the wire contract says so, and a
	// fake that returned an error here would let a tool get away with
	// treating a legitimate `found: false` as a failure.
	return ports.SpeechMatch{Found: false, Index: len(f.spoken)}, nil
}

func (f *FakeSpeechReader) WaitForSpeechToFinish(timeout time.Duration) (bool, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	if f.err != nil {
		return false, f.err
	}
	return f.finished, nil
}
