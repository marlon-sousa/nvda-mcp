// screenreader-mcp domain -- the announce tool.
// Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
//
// ROLE: controller, one per tool. GATED on `announce`.
// USES: ports.Announcer, through ToolContext.Announcer().
// LISTED BY: registry.go.
//
// The only tool that addresses a HUMAN. Everything else here observes or drives
// a screen reader; this speaks to the person in front of it, through the
// reader's real synthesizer and UNDERNEATH whatever suppression the capture mode
// has in place -- which is the whole point, because the mode where the agent
// most needs to say something is the mode where the tester can hear nothing
// else.
//
// The description below carries the operational warning, and has to: in `silent`
// mode the tester can hear this announcement and then nothing further, cannot
// navigate, and cannot reply. Until entry 11.2 lands there is no reply channel
// at all, so an announcement in a silent session must TELL, never ASK, and
// should name the panic gesture as the way out. An agent that reads this tool as
// a chat channel will strand somebody.
package tools

import (
	"encoding/json"
	"errors"
	"strings"

	"github.com/marlon-sousa/screen-readers-mcp/server/domain/entities"
)

// Announce speaks a message to the human operating the reader.
type Announce struct{}

var _ Tool = (*Announce)(nil)

func (t *Announce) Name() string { return "announce" }

func (t *Announce) Capability() entities.Capability { return entities.CapabilityAnnounce }

func (t *Announce) Description() string {
	return "Speak a short message OUT LOUD to the human sitting at the screen reader. " +
		"This reaches a person, not a log: it interrupts them, so use it when you " +
		"genuinely need their attention and not to narrate your progress. It is " +
		"audible even in silent capture mode, where the reader's own speech is " +
		"suppressed -- that is what it is for. IMPORTANT: in silent mode the human " +
		"can hear this and nothing else. They cannot read the screen, cannot reach " +
		"your chat window, and have no way to reply to you. So in silent mode, TELL " +
		"them something (\"I am stuck on a password field; press NVDA+control+shift+b " +
		"to stop the bridge and take over\") rather than asking a question you cannot " +
		"receive an answer to. In live mode the reader is speaking normally, so the " +
		"human can hear their way to your chat window and answer you there."
}

func (t *Announce) InputSchema() json.RawMessage {
	return json.RawMessage(`{
	"type": "object",
	"properties": {
		"text": {
			"type": "string",
			"minLength": 1,
			"description": "What to say. Keep it to a sentence or two -- it is spoken aloud and interrupts the person, and a long message is hard to hold in memory by ear. Say what you need and what you want them to do about it."
		}
	},
	"required": ["text"],
	"additionalProperties": false
}`)
}

type announceParams struct {
	Text string `json:"text"`
}

type announceResult struct {
	Announced string `json:"announced"`
}

func (t *Announce) Execute(ctx ToolContext, params json.RawMessage) (any, error) {
	announcer, err := ctx.Announcer()
	if err != nil {
		return nil, err
	}
	var request announceParams
	if err := decodeParams(params, &request); err != nil {
		return nil, err
	}
	// Rejected before the port is touched: an empty announcement is two cue
	// beeps followed by silence, which a tester reads as a malfunction of the
	// one channel they are relying on.
	if strings.TrimSpace(request.Text) == "" {
		return nil, errors.New("text is required, and must not be empty or whitespace")
	}

	if err := announcer.Announce(request.Text); err != nil {
		return nil, err
	}
	// Echo what was spoken, as press_gesture echoes its ids: the reader returns
	// only an acknowledgement, so the useful confirmation is that this exact
	// text reached it.
	return announceResult{Announced: request.Text}, nil
}
