// screenreader-mcp fakes -- the fakes' own sentinel errors.
// Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
//
// ROLE: supporting construct for the fakes. Not a port double, so it carries no
// compile-time assertion.
//
// A fake that was asked for something nobody scripted must FAIL rather than
// invent a plausible answer: an invented answer would let a test pass while
// exercising a code path the author never described.
package fakes

import "errors"

var errNothingScripted = errors.New("fake: nothing was scripted for this call")
