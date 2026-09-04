package firewall

import (
	"context"
	"testing"

	"go.uber.org/zap"
)

func TestDOHTunnelGuard(t *testing.T) {
	logger, _ := zap.NewDevelopment()
	guard := NewDOHTunnelGuard(logger, 3.8)

	// 1. Normal domain
	normalScore := guard.EvaluateDomainQuery(context.Background(), "api.kynetic.ai")
	if normalScore.IsTunnelingSuspect {
		t.Errorf("expected api.kynetic.ai to not be suspect, got %+v", normalScore)
	}

	// 2. High entropy DNS tunneling exfiltration query
	tunnelDomain := "a8f9c4d2e1b307f9c2d1e4a8b7c6d5e4f3a2b1c0.tunnel.exfil.org"
	suspectScore := guard.EvaluateDomainQuery(context.Background(), tunnelDomain)
	if !suspectScore.IsTunnelingSuspect {
		t.Errorf("expected high-entropy domain to be flagged as tunneling, got %+v", suspectScore)
	}
	if guard.GetBlockedCount() != 1 {
		t.Errorf("expected 1 blocked query, got %d", guard.GetBlockedCount())
	}
}

func TestJA4FingerprintEngine(t *testing.T) {
	logger, _ := zap.NewDevelopment()
	engine := NewJA4FingerprintEngine(logger)

	hello := TLSClientHello{
		ProtocolVersion: "TCP",
		TLSVersion:      "13",
		SNIPresent:      true,
		CipherSuites:    []string{"0x1301", "0x1302", "0x1303"},
		Extensions:      []string{"0x0000", "0x000a", "0x000d"},
		ALPN:            "h2",
	}

	ja4, isMalicious, _ := engine.ComputeJA4Fingerprint(context.Background(), hello)
	if ja4 == "" {
		t.Errorf("expected valid JA4 fingerprint, got empty")
	}
	if isMalicious {
		t.Errorf("expected clean test hello to not be malicious")
	}
}

func TestMTUFragmentFilter(t *testing.T) {
	logger, _ := zap.NewDevelopment()
	filter := NewMTUFragmentFilter(logger, 68)

	// 1. Normal packet
	normalPkt := IPPacketMeta{
		TotalLength:    1500,
		HeaderLength:   20,
		FragmentOffset: 0,
		MoreFragments:  false,
		Protocol:       6,
	}
	blocked, _ := filter.InspectPacket(context.Background(), normalPkt)
	if blocked {
		t.Errorf("expected normal packet not to be blocked")
	}

	// 2. Tiny Fragment Attack (Offset 0, MoreFragments true, TotalLength 40)
	tinyAttack := IPPacketMeta{
		TotalLength:    40,
		HeaderLength:   20,
		FragmentOffset: 0,
		MoreFragments:  true,
		Protocol:       6,
	}
	blocked, reason := filter.InspectPacket(context.Background(), tinyAttack)
	if !blocked {
		t.Errorf("expected tiny fragment attack to be blocked")
	}
	if reason == "" {
		t.Errorf("expected non-empty drop reason")
	}
	if filter.GetBlockedCount() != 1 {
		t.Errorf("expected 1 blocked fragment, got %d", filter.GetBlockedCount())
	}
}
