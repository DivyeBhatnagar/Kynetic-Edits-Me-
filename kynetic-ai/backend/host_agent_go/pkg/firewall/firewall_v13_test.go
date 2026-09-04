package firewall

import (
	"testing"
	"time"

	"go.uber.org/zap"
)

func TestODoHResolver(t *testing.T) {
	logger := zap.NewNop()
	resolver, err := NewODoHResolver(logger, "", "", nil)
	if err != nil {
		t.Fatalf("NewODoHResolver failed: %v", err)
	}

	query, err := resolver.EncryptODoHQuery("api.kynetic.ai")
	if err != nil {
		t.Fatalf("EncryptODoHQuery failed: %v", err)
	}
	if len(query.EncryptedPayload) == 0 {
		t.Fatalf("expected non-empty encrypted query payload")
	}

	resp, err := resolver.ResolveDomain("api.kynetic.ai")
	if err != nil {
		t.Fatalf("ResolveDomain failed: %v", err)
	}
	if len(resp.ResolvedIP) == 0 || !resp.DNSSecOK {
		t.Fatalf("expected valid resolved IP and DNSSEC flag")
	}
}

func TestZeroRTTReplayGuard(t *testing.T) {
	logger := zap.NewNop()
	guard := NewZeroRTTReplayGuard(logger, 2*time.Second)

	ticketID := []byte("tls13_resumption_ticket_nonce_abc")
	now := time.Now()

	// 1st request -> valid
	ok, err := guard.ValidateEarlyDataTicket(ticketID, now)
	if err != nil || !ok {
		t.Fatalf("first 0-RTT validation should succeed")
	}

	// 2nd request (replay) -> rejected
	ok, err = guard.ValidateEarlyDataTicket(ticketID, now)
	if err == nil || ok {
		t.Fatalf("replayed 0-RTT validation must fail")
	}

	// Expired timestamp -> rejected
	oldTimestamp := now.Add(-10 * time.Second)
	ok, err = guard.ValidateEarlyDataTicket([]byte("another_ticket"), oldTimestamp)
	if err == nil || ok {
		t.Fatalf("expired 0-RTT ticket must fail")
	}
}
