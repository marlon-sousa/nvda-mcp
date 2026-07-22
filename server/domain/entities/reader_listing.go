// screenreader-mcp domain -- ReaderListing: what `list_readers` answers.
// Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
//
// ROLE: entity. The configured readers joined with what the probe could learn
// about their endpoints. Pure -- the join lives here rather than in the tool, so
// the rule "an endpoint we did not configure is never reported" is a property of
// the model and not of one caller.
// BUILT BY: BuildListing, called by 10b's connection controller with the
// configured readers and the probe's answer.
// READ BY: the `list_readers` tool.
package entities

// Liveness is how much can be said about an endpoint without dialing it.
type Liveness string

const (
	// Listening: a bridge is listening there right now.
	Listening Liveness = "listening"

	// NotListening: this endpoint is knowable and nothing is listening.
	NotListening Liveness = "not listening"

	// LivenessUnknown: it cannot be known without connecting, which we will
	// not do -- the bridge serves one session at a time, so a probing dial
	// would occupy the very slot the agent wants. Every TCP endpoint reports
	// this.
	LivenessUnknown Liveness = "unknown"
)

// EndpointStatus is one endpoint and what is known about it.
type EndpointStatus struct {
	Endpoint Endpoint
	Liveness Liveness
}

// ReaderStatus is one configured reader with its endpoints, in declared order --
// the same order connect_reader will try them in.
type ReaderStatus struct {
	Name      string
	Endpoints []EndpointStatus
}

// ReaderListing is the whole answer.
type ReaderListing struct {
	Readers []ReaderStatus
}

// BuildListing joins the configured readers with the endpoints the probe found
// live.
//
// The join is one-directional on purpose: it walks the CONFIGURED readers and
// asks the live set about each, never the other way round. A pipe that is
// listening but belongs to no configured reader is therefore absent from the
// answer, which is spec 0013's determinism rule expressed as code rather than
// as a review comment.
//
// Only endpoints whose kind can be probed at all are reported live-or-not; the
// rest report LivenessUnknown, so "not listening" always means the probe
// actually looked.
func BuildListing(readers []ConfiguredReader, live []Endpoint) ReaderListing {
	liveSet := make(map[Endpoint]struct{}, len(live))
	for _, e := range live {
		liveSet[e] = struct{}{}
	}

	listing := ReaderListing{Readers: make([]ReaderStatus, 0, len(readers))}
	for _, reader := range readers {
		status := ReaderStatus{Name: reader.Name, Endpoints: make([]EndpointStatus, 0, len(reader.Endpoints))}
		for _, endpoint := range reader.Endpoints {
			status.Endpoints = append(status.Endpoints, EndpointStatus{
				Endpoint: endpoint,
				Liveness: liveness(endpoint, liveSet),
			})
		}
		listing.Readers = append(listing.Readers, status)
	}
	return listing
}

// liveness applies the per-kind rule: a pipe can be answered for, a socket
// cannot.
func liveness(endpoint Endpoint, live map[Endpoint]struct{}) Liveness {
	if endpoint.Kind != TransportPipe {
		return LivenessUnknown
	}
	if _, ok := live[endpoint]; ok {
		return Listening
	}
	return NotListening
}
