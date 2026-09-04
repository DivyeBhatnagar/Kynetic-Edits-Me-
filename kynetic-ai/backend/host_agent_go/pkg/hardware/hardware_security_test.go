package hardware_test

import (
	"testing"
	"time"

	"github.com/kynetic-ai/host-agent/pkg/hardware"
)

func TestIOMMUGroupsCheck(t *testing.T) {
	status, err := hardware.CheckIOMMUGroups()
	if err != nil {
		t.Fatalf("unexpected error checking IOMMU: %v", err)
	}
	if status == nil {
		t.Fatal("expected non-nil IOMMUGovStatus")
	}
}

func TestThermalGovernor(t *testing.T) {
	limits := &hardware.ThermalLimits{
		MaxCoreTempC:     80.0,
		MaxHotspotTempC:  90.0,
		MaxSustainedSecs: 1,
	}
	gov := hardware.NewThermalGovernor(limits)

	// Normal temperature
	action, err := gov.EvaluateSample(hardware.GPUTelemetry{TemperatureC: 70.0})
	if err != nil || action != "NORMAL" {
		t.Fatalf("expected NORMAL, got %s (err: %v)", action, err)
	}

	// Overheat triggers THROTTLE first
	action, _ = gov.EvaluateSample(hardware.GPUTelemetry{TemperatureC: 85.0})
	if action != "THROTTLE" {
		t.Fatalf("expected THROTTLE, got %s", action)
	}

	// Sustained overheat triggers TRIPWIRE_TERMINATE after threshold
	time.Sleep(1100 * time.Millisecond)
	action, err = gov.EvaluateSample(hardware.GPUTelemetry{TemperatureC: 85.0})
	if action != "TRIPWIRE_TERMINATE" || err == nil {
		t.Fatalf("expected TRIPWIRE_TERMINATE with error, got %s", action)
	}
	if !gov.IsTripwireActive() {
		t.Fatal("expected tripwire to be active")
	}
}

func TestVRAMSanitizer(t *testing.T) {
	receipt, err := hardware.SanitizeGPUVRAM(0, "NVIDIA GeForce RTX 4090", 24576)
	if err != nil {
		t.Fatalf("unexpected sanitization error: %v", err)
	}
	if receipt.Status != "VERIFIED_ZEROIZED" {
		t.Fatalf("expected status VERIFIED_ZEROIZED, got %s", receipt.Status)
	}
	if receipt.ReceiptHash == "" {
		t.Fatal("expected non-empty receipt cryptographic hash")
	}
}
