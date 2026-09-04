package firewall

import (
	"testing"
)

func TestRoCEPFCFilter(t *testing.T) {
	cfg := RoCEPFCFilterConfig{
		MaxPauseFramesPerSec:      5,
		MaxConsecutivePauseQuanta: 1000,
	}
	filter := NewRoCEPFCFilter(cfg)

	// Ingest under threshold
	for i := 0; i < 5; i++ {
		ok, _ := filter.IngestPFCFrame(RoCEv2PFCFrame{
			PriorityClass:       3,
			PauseDurationQuanta: 100,
			SrcMAC:              "00:11:22:33:44:55",
			TimestampMicrosec:   1000,
		})
		if !ok {
			t.Fatalf("frame within limit rejected")
		}
	}

	// Exceed limit -> PFC storm detected
	okBad, msgBad := filter.IngestPFCFrame(RoCEv2PFCFrame{
		PriorityClass:       3,
		PauseDurationQuanta: 100,
		SrcMAC:              "00:11:22:33:44:55",
		TimestampMicrosec:   1000,
	})
	if okBad {
		t.Fatalf("PFC storm attack was allowed: %s", msgBad)
	}
}
