// screenreader-mcp fakes -- FakeFocusInspector: the FocusInspector port double.
// Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
//
// ROLE: test double. MIRRORS domain/ports/focus_inspector.go.
// USED BY: 10b's get_focus_info tool controller tests.
package fakes

import (
	"sync"

	"github.com/marlon-sousa/screen-readers-mcp/server/domain/ports"
)

// FakeFocusInspector reports whatever focus a test put there.
type FakeFocusInspector struct {
	mu    sync.Mutex
	focus ports.FocusInfo
	err   error
}

var _ ports.FocusInspector = (*FakeFocusInspector)(nil)

// NewFakeFocusInspector builds an inspector reporting an empty focus.
func NewFakeFocusInspector() *FakeFocusInspector { return &FakeFocusInspector{} }

// SetFocus is what the next read will report. The role and state strings are
// the reader's own vocabulary, so a test writes NVDA's or JAWS's spelling and
// the code under test must not care which.
func (f *FakeFocusInspector) SetFocus(focus ports.FocusInfo) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.focus = focus
}

// FailWith makes every read return err.
func (f *FakeFocusInspector) FailWith(err error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.err = err
}

func (f *FakeFocusInspector) FocusInfo() (ports.FocusInfo, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	if f.err != nil {
		return ports.FocusInfo{}, f.err
	}
	return f.focus, nil
}
