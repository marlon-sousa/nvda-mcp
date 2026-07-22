// screenreader-mcp fakes -- FakeGestureSender: the GestureSender port double.
// Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
//
// ROLE: test double. MIRRORS domain/ports/gesture_sender.go.
// USED BY: 10b's press_gesture tool controller tests.
//
// This one records, and legitimately so: pressing a gesture has no return value
// worth asserting on, so "which ids were sent, in which order" IS the
// requirement. That is a spy in a hand-written fake, not a mock framework.
package fakes

import (
	"sync"

	"github.com/marlon-sousa/screen-readers-mcp/server/domain/ports"
)

// FakeGestureSender records the gestures it was asked to press.
type FakeGestureSender struct {
	mu      sync.Mutex
	pressed [][]string
	err     error
}

var _ ports.GestureSender = (*FakeGestureSender)(nil)

// NewFakeGestureSender builds a sender that accepts everything.
func NewFakeGestureSender() *FakeGestureSender { return &FakeGestureSender{} }

// FailWith makes every press return err, as a reader that rejected an unknown
// gesture id would.
func (f *FakeGestureSender) FailWith(err error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.err = err
}

// Pressed is every call's id list, in order.
func (f *FakeGestureSender) Pressed() [][]string {
	f.mu.Lock()
	defer f.mu.Unlock()
	return append([][]string(nil), f.pressed...)
}

func (f *FakeGestureSender) PressGestures(ids []string) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	if f.err != nil {
		return f.err
	}
	f.pressed = append(f.pressed, append([]string(nil), ids...))
	return nil
}
