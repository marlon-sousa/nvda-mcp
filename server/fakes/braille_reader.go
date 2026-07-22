// screenreader-mcp fakes -- FakeBrailleReader: the BrailleReader port double.
// Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
//
// ROLE: test double. MIRRORS domain/ports/braille_reader.go.
// USED BY: 10b's get_braille tool controller tests.
//
// Note what it is NOT for: a reader without braille is tested by handing over no
// BrailleReader at all, which is the whole point of splitting the ports by
// capability. This fake stands in for a reader that HAS braille.
package fakes

import (
	"strings"
	"sync"

	"github.com/marlon-sousa/screen-readers-mcp/server/domain/ports"
)

// FakeBrailleReader is an in-memory braille log.
type FakeBrailleReader struct {
	mu      sync.Mutex
	brailed []string
	err     error
}

var _ ports.BrailleReader = (*FakeBrailleReader)(nil)

// NewFakeBrailleReader builds an empty log.
func NewFakeBrailleReader() *FakeBrailleReader { return &FakeBrailleReader{} }

// Braille appends what the display showed.
func (f *FakeBrailleReader) Braille(text ...string) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.brailed = append(f.brailed, text...)
}

// FailWith makes every call return err.
func (f *FakeBrailleReader) FailWith(err error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.err = err
}

func (f *FakeBrailleReader) BrailleSince(sinceIndex int) (ports.BrailleRange, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	if f.err != nil {
		return ports.BrailleRange{}, f.err
	}
	if sinceIndex < 0 {
		sinceIndex = 0
	}
	if sinceIndex > len(f.brailed) {
		sinceIndex = len(f.brailed)
	}
	return ports.BrailleRange{
		Text:      strings.Join(f.brailed[sinceIndex:], "\n"),
		FromIndex: sinceIndex,
		ToIndex:   len(f.brailed),
	}, nil
}
