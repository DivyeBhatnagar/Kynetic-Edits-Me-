package firewall

import (
	"context"
	"testing"
	"time"

	"go.uber.org/zap"
)

func TestISPGuard(t *testing.T) {
	logger, _ := zap.NewDevelopment()
	guard := NewISPGuard(logger)

	// 1. Normal traffic profile
	normalStats := TrafficStats{
		OutboundPPS:   1000,
		OutboundBPS:   1000000,
		SynPacketRate: 50,
		LastAudited:   time.Now(),
	}
	violation, reason := guard.EvaluateTraffic(context.Background(), normalStats)
	if violation {
		t.Fatalf("expected no violation for normal traffic, got: %s", reason)
	}
	if guard.IsThrottling() {
		t.Errorf("expected guard not throttling")
	}

	// 2. SYN flood / port scanning abuse
	synFloodStats := TrafficStats{
		OutboundPPS:   2000,
		SynPacketRate: 9999, // Exceeds 500
	}
	violation, reason = guard.EvaluateTraffic(context.Background(), synFloodStats)
	if !violation {
		t.Fatalf("expected violation for SYN flood, got none")
	}
	if !guard.IsThrottling() {
		t.Errorf("expected guard to be throttling")
	}

	// 3. Prohibited port (Port 25 SMTP spam)
	smtpStats := TrafficStats{
		OutboundPPS:      50,
		BlacklistedPorts: []int{25},
	}
	violation, reason = guard.EvaluateTraffic(context.Background(), smtpStats)
	if !violation {
		t.Fatalf("expected violation for port 25 egress, got none")
	}

	if guard.GetViolationCount() != 2 {
		t.Errorf("expected 2 violations, got %d", guard.GetViolationCount())
	}
}
