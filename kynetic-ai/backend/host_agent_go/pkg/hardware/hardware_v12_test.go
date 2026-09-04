package hardware

import (
	"context"
	"os"
	"path/filepath"
	"testing"

	"go.uber.org/zap"
)

func TestVoltageFaultDetector(t *testing.T) {
	logger, _ := zap.NewDevelopment()
	tempDir := t.TempDir()

	hwmon0 := filepath.Join(tempDir, "hwmon0")
	_ = os.MkdirAll(hwmon0, 0755)
	// Normal 1100mV
	_ = os.WriteFile(filepath.Join(hwmon0, "in0_input"), []byte("1100\n"), 0644)

	detector := NewVoltageFaultDetector(logger, tempDir, 1100)
	status, err := detector.AuditVoltageRegulators(context.Background())
	if err != nil {
		t.Fatalf("AuditVoltageRegulators failed: %v", err)
	}
	if status.FaultDetected {
		t.Errorf("expected no fault detected for normal voltage")
	}

	// Simulated severe undervolting dip: 800mV (27% dip)
	_ = os.WriteFile(filepath.Join(hwmon0, "in0_input"), []byte("800\n"), 0644)
	status, err = detector.AuditVoltageRegulators(context.Background())
	if err != nil {
		t.Fatalf("AuditVoltageRegulators failed: %v", err)
	}
	if !status.FaultDetected || detector.GetFaultCount() != 1 {
		t.Errorf("expected fault injection detected for 800mV, got %+v", status)
	}
}

func TestNVLinkGuard(t *testing.T) {
	logger, _ := zap.NewDevelopment()
	tempDir := t.TempDir()

	link0 := filepath.Join(tempDir, "nvlink", "link0")
	_ = os.MkdirAll(link0, 0755)
	_ = os.WriteFile(filepath.Join(link0, "encryption"), []byte("enabled\n"), 0644)

	guard := NewNVLinkGuard(logger, tempDir)
	status, err := guard.AuditNVLinkTopology(context.Background())
	if err != nil {
		t.Fatalf("AuditNVLinkTopology failed: %v", err)
	}
	if status.TotalLinks != 1 || status.EncryptedLinks != 1 {
		t.Errorf("expected 1 encrypted link, got %+v", status)
	}
}

func TestTMESMEEnforcer(t *testing.T) {
	logger, _ := zap.NewDevelopment()
	cpuFile := filepath.Join(t.TempDir(), "cpuinfo")
	_ = os.WriteFile(cpuFile, []byte("flags: fpu vme de pse tsc msr pae mce cx8 apic sep tme\n"), 0644)

	enforcer := NewTMESMEEnforcer(logger, cpuFile)
	status, err := enforcer.AuditMemoryEncryption(context.Background())
	if err != nil {
		t.Fatalf("AuditMemoryEncryption failed: %v", err)
	}
	if !status.Supported || status.Standard != "intel_tme" {
		t.Errorf("expected intel_tme supported, got %+v", status)
	}
}

func TestThermalDitherManager(t *testing.T) {
	logger, _ := zap.NewDevelopment()
	mgr := NewThermalDitherManager(logger, 2.5)

	fuzzed := mgr.DitherFanSpeed(context.Background(), 60.0)
	if fuzzed < 55.0 || fuzzed > 65.0 {
		t.Errorf("fuzzed fan speed %f out of expected range", fuzzed)
	}
	if mgr.GetDitherEventsCount() != 1 {
		t.Errorf("expected 1 dither event, got %d", mgr.GetDitherEventsCount())
	}
}

func TestMicrocodeGuard(t *testing.T) {
	logger, _ := zap.NewDevelopment()
	tempDir := t.TempDir()

	_ = os.WriteFile(filepath.Join(tempDir, "microcode"), []byte("mock ucode"), 0660)
	guard := NewMicrocodeGuard(logger, tempDir)

	locked, err := guard.EnforceMicrocodeLockdown(context.Background())
	if err != nil {
		t.Fatalf("EnforceMicrocodeLockdown failed: %v", err)
	}
	if len(locked) != 1 || !guard.IsGuarded() {
		t.Errorf("expected microcode node locked, got %v", locked)
	}
}
