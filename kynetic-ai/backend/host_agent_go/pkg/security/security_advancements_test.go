package security_test

import (
	"testing"

	"github.com/kynetic-ai/host-agent/pkg/security"
)

func TestEBPFProbeManager(t *testing.T) {
	mgr := security.NewEBPFProbeManager()
	anomaly := mgr.RecordAnomaly(1234, "mount", "/dev/mem")
	if anomaly.ActionTaken != "BLOCKED" {
		t.Fatalf("expected BLOCKED, got %s", anomaly.ActionTaken)
	}

	anomalies := mgr.GetRecentAnomalies()
	if len(anomalies) != 1 {
		t.Fatalf("expected 1 anomaly, got %d", len(anomalies))
	}
}

func TestKSMShield(t *testing.T) {
	status, err := security.CheckAndDisableKSM()
	if err != nil {
		t.Fatalf("unexpected KSM error: %v", err)
	}
	if status == nil {
		t.Fatal("expected non-nil KSM status")
	}
}

func TestIMASecureBoot(t *testing.T) {
	status := security.CheckIMAAndSecureBoot()
	if status == nil {
		t.Fatal("expected non-nil IMAStatus")
	}
}

func TestOperatorKillSwitchAndCanary(t *testing.T) {
	sw := security.NewOperatorKillSwitch()
	canary, err := sw.PlantCanary("canary-test-1")
	if err != nil {
		t.Fatalf("failed to plant canary: %v", err)
	}
	if canary == nil {
		t.Fatal("expected non-nil canary trap")
	}

	// Verify untampered canary
	ok, err := sw.VerifyCanaries()
	if !ok || err != nil {
		t.Fatalf("expected valid canaries, got ok=%v, err=%v", ok, err)
	}

	// Tamper with canary memory buffer
	canary.Buffer[10] = 0xAA
	canary.Buffer[0] = 0xFF // corrupt magic word
	ok, err = sw.VerifyCanaries()
	if ok || err == nil {
		t.Fatal("expected canary tampering to be caught")
	}
	if !sw.IsTriggered {
		t.Fatal("expected kill switch to be triggered by canary corruption")
	}
}
