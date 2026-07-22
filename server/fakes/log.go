// screenreader-mcp fakes -- FakeLog: the Log port double.
// Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
//
// ROLE: test double. MIRRORS domain/ports/log.go.
// USED BY: tests only.
//
// It records rather than prints, for a reason beyond tidiness: a test that let
// its log reach a stream would be a test that proves nothing about the one rule
// this port exists for -- that nothing but MCP frames reaches stdout.
package fakes

import (
	"fmt"
	"sync"

	"github.com/marlon-sousa/screen-readers-mcp/server/domain/ports"
)

// FakeLog keeps every line it was given.
type FakeLog struct {
	mu    sync.Mutex
	lines []string
}

var _ ports.Log = (*FakeLog)(nil)

// NewFakeLog builds an empty log.
func NewFakeLog() *FakeLog { return &FakeLog{} }

func (l *FakeLog) Debugf(format string, args ...any) { l.record("debug", format, args...) }

func (l *FakeLog) Infof(format string, args ...any) { l.record("info", format, args...) }

func (l *FakeLog) Errorf(format string, args ...any) { l.record("error", format, args...) }

// Lines is every line recorded, in order, each prefixed with its level.
func (l *FakeLog) Lines() []string {
	l.mu.Lock()
	defer l.mu.Unlock()
	return append([]string(nil), l.lines...)
}

func (l *FakeLog) record(level, format string, args ...any) {
	l.mu.Lock()
	defer l.mu.Unlock()
	l.lines = append(l.lines, level+": "+fmt.Sprintf(format, args...))
}
