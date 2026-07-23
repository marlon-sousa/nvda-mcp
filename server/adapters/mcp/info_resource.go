// screenreader-mcp adapters -- the screenreader://info resource.
// Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
//
// ROLE: adapter. Serves `screenreader://info` from the current session.
// BUILT BY: sdk_server.go's Bind. DEPENDS ON: a SessionSource, satisfied by
// domain/controllers/connection.go.
//
// This is spec 0013's second capability mechanism, and spec 0005's principle 2:
// SURFACE THE READER. The agent already knows NVDA's browse and focus modes and
// JAWS's forms mode from its training -- so hand it the reader's name and
// version and let it apply what it knows, rather than teaching this server to
// have opinions about particular readers.
//
// A RESOURCE rather than `initialize.instructions`, which was considered and
// rejected: instructions are frozen at handshake time, and the bridge usually
// connects long afterwards. A resource is read when the agent wants it and
// always describes the session that exists now.
package mcp

import (
	"context"
	"encoding/json"

	sdk "github.com/modelcontextprotocol/go-sdk/mcp"

	"github.com/marlon-sousa/screen-readers-mcp/server/domain/entities"
	"github.com/marlon-sousa/screen-readers-mcp/server/domain/ports"
)

// InfoURI is the resource's address.
const InfoURI = "screenreader://info"

// SessionSource is what the resource reads.
//
// Declared here, in the consumer, and narrow: this adapter may look at the
// current session and the connection state, and at nothing else. Satisfied by
// the connection controller.
type SessionSource interface {
	Current() *ports.ReaderConnection
	Status() entities.ConnectionStatus
}

// info is the resource's document. Its own shape, because it is agent-facing
// text and should change when we mean it to rather than when a domain field is
// renamed.
type info struct {
	State  string `json:"state"`
	Reason string `json:"reason,omitempty"`

	Reader        string   `json:"reader,omitempty"`
	ReaderVersion string   `json:"readerVersion,omitempty"`
	Endpoint      string   `json:"endpoint,omitempty"`
	Capabilities  []string `json:"capabilities,omitempty"`
	Mode          string   `json:"mode,omitempty"`
	Synth         string   `json:"synth,omitempty"`

	// The two session artifacts, as PATHS. Their contents are deliberately
	// not exposed as resources in v1 (spec 0013, out of scope): reading a
	// transcript through the agent is worth having and needs its own
	// conversation, not least about what it means once a bridge is not on the
	// same machine as the server.
	LogPath       string `json:"logPath,omitempty"`
	ReaderLogPath string `json:"readerLogPath,omitempty"`

	ProtocolVersion int `json:"protocolVersion,omitempty"`
}

// addInfoResource registers the resource. It is always present, whether or not a
// session is: an agent asking "what am I connected to?" deserves the answer
// "nothing, and here is why" rather than a missing resource.
func (s *Server) addInfoResource(sessions SessionSource) {
	s.sdk.AddResource(
		&sdk.Resource{
			URI:      InfoURI,
			Name:     "screen reader session",
			MIMEType: "application/json",
			Description: "Which screen reader is connected, what it announced it can do, " +
				"the capture mode in effect, and where this session's two log files are. " +
				"Read this to learn which reader you are driving, then apply what you " +
				"already know about that reader.",
		},
		func(_ context.Context, _ *sdk.ReadResourceRequest) (*sdk.ReadResourceResult, error) {
			document, err := json.MarshalIndent(describe(sessions), "", "  ")
			if err != nil {
				return nil, err
			}
			return &sdk.ReadResourceResult{Contents: []*sdk.ResourceContents{{
				URI:      InfoURI,
				MIMEType: "application/json",
				Text:     string(document),
			}}}, nil
		},
	)
}

// describe builds the document from whatever is currently true.
func describe(sessions SessionSource) info {
	status := sessions.Status()
	document := info{State: status.State.String(), Reason: status.Reason}

	connection := sessions.Current()
	if connection == nil {
		return document
	}

	session := connection.Session
	document.Reader = session.Reader.Name
	document.ReaderVersion = session.Reader.Version
	document.Endpoint = connection.Endpoint.String()
	document.Capabilities = session.Capabilities.Strings()
	document.Mode = session.Mode.String()
	document.Synth = session.Synth
	document.LogPath = session.LogPath
	document.ReaderLogPath = session.ReaderLogPath
	document.ProtocolVersion = session.ProtocolVersion
	return document
}
