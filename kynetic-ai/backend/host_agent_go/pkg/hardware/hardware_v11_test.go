package hardware

import (
	"context"
	"os"
	"path/filepath"
	"testing"

	"go.uber.org/zap"
)

func TestNvidiaCCManager(t *testing.T) {
	logger, _ := zap.NewDevelopment()
	tempDir := t.TempDir()

	_ = os.WriteFile(filepath.Join(tempDir, "cc_mode"), []byte("on\n"), 0644)
	mgr := NewNvidiaCCManager(logger, tempDir)

	mode, err := mgr.QueryCCMode(context.Background())
	if err != nil {
		t.Fatalf("QueryCCMode failed: %v", err)
	}
	if mode != CCModeOn || !mgr.IsConfidentialComputeActive() {
		t.Errorf("expected CCModeOn, got %s", mode)
	}
}

func TestEnclaveMemoryManager(t *testing.T) {
	logger, _ := zap.NewDevelopment()
	cpuFile := filepath.Join(t.TempDir(), "cpuinfo")
	_ = os.WriteFile(cpuFile, []byte("flags: fpu vme de pse tsc msr pae mce cx8 apic sep sev_snp\n"), 0644)

	mgr := NewEnclaveMemoryManager(logger, cpuFile)
	encType, err := mgr.DetectHardwareEnclaves(context.Background())
	if err != nil {
		t.Fatalf("DetectHardwareEnclaves failed: %v", err)
	}
	if encType != EnclaveSEVSNP {
		t.Errorf("expected EnclaveSEVSNP, got %s", encType)
	}
}

func TestCoreIsolationManager(t *testing.T) {
	logger, _ := zap.NewDevelopment()
	tempDir := t.TempDir()
	smtDir := filepath.Join(tempDir, "smt")
	_ = os.MkdirAll(smtDir, 0755)
	_ = os.WriteFile(filepath.Join(smtDir, "control"), []byte("on\n"), 0644)

	mgr := NewCoreIsolationManager(logger, tempDir)
	status, err := mgr.QuerySMTControl()
	if err != nil {
		t.Fatalf("QuerySMTControl failed: %v", err)
	}
	if status != "on" {
		t.Errorf("expected 'on', got '%s'", status)
	}

	err = mgr.DisableSMT(context.Background())
	if err != nil {
		t.Fatalf("DisableSMT failed: %v", err)
	}
	if !mgr.IsSMTDisabled() {
		t.Errorf("expected IsSMTDisabled == true")
	}
}

func TestUSBGuard(t *testing.T) {
	logger, _ := zap.NewDevelopment()
	tempDir := t.TempDir()

	dev1 := filepath.Join(tempDir, "1-1")
	_ = os.MkdirAll(dev1, 0755)
	_ = os.WriteFile(filepath.Join(dev1, "authorized"), []byte("1\n"), 0644)

	guard := NewUSBGuard(logger, tempDir)
	locked, err := guard.LockUSBDevices(context.Background())
	if err != nil {
		t.Fatalf("LockUSBDevices failed: %v", err)
	}
	if len(locked) != 1 || locked[0] != "1-1" {
		t.Errorf("expected 1 locked USB device, got %v", locked)
	}
}

func TestThunderboltDMAGuard(t *testing.T) {
	logger, _ := zap.NewDevelopment()
	tempDir := t.TempDir()

	tbDev := filepath.Join(tempDir, "domain0")
	_ = os.MkdirAll(tbDev, 0755)
	_ = os.WriteFile(filepath.Join(tbDev, "authorized"), []byte("1\n"), 0644)

	guard := NewThunderboltDMAGuard(logger, tempDir)
	isolated, err := guard.EnforceDMAPolicy(context.Background())
	if err != nil {
		t.Fatalf("EnforceDMAPolicy failed: %v", err)
	}
	if len(isolated) != 1 {
		t.Errorf("expected 1 isolated Thunderbolt domain, got %d", len(isolated))
	}
}

func TestPCIeTLPGuard(t *testing.T) {
	logger, _ := zap.NewDevelopment()
	tempDir := t.TempDir()

	pciDev := filepath.Join(tempDir, "0000:00:01.0")
	_ = os.MkdirAll(pciDev, 0755)
	_ = os.WriteFile(filepath.Join(pciDev, "aer_dev_correctable"), []byte("3\n"), 0644)
	_ = os.WriteFile(filepath.Join(pciDev, "aer_dev_fatal"), []byte("0\n"), 0644)

	guard := NewPCIeTLPGuard(logger, tempDir)
	report, err := guard.AuditAERStatus(context.Background())
	if err != nil {
		t.Fatalf("AuditAERStatus failed: %v", err)
	}
	if report.CorrectableErrors != 3 || report.PoisonedTLPDetected {
		t.Errorf("unexpected report: %+v", report)
	}
}

func TestUEFICapsuleLock(t *testing.T) {
	logger, _ := zap.NewDevelopment()
	tempDir := t.TempDir()

	_ = os.WriteFile(filepath.Join(tempDir, "mtd0"), []byte("mock mtd"), 0660)
	lock := NewUEFICapsuleLock(logger, tempDir, "")

	err := lock.EnforceCapsuleLockdown(context.Background())
	if err != nil {
		t.Fatalf("EnforceCapsuleLockdown failed: %v", err)
	}
	if !lock.IsCapsuleLocked() {
		t.Errorf("expected IsCapsuleLocked == true")
	}
}

func TestBMCAirgapManager(t *testing.T) {
	logger, _ := zap.NewDevelopment()
	tempDir := t.TempDir()

	_ = os.WriteFile(filepath.Join(tempDir, "ipmi0"), []byte("mock ipmi"), 0660)
	mgr := NewBMCAirgapManager(logger, tempDir)

	isolated, err := mgr.EnforceBMCAirgap(context.Background())
	if err != nil {
		t.Fatalf("EnforceBMCAirgap failed: %v", err)
	}
	if len(isolated) != 1 {
		t.Errorf("expected 1 BMC node isolated, got %d", len(isolated))
	}
}

func TestGEMMNoiseInjector(t *testing.T) {
	logger, _ := zap.NewDevelopment()
	injector := NewGEMMNoiseInjector(logger, 20)

	d := injector.ApplyJitterDelay(context.Background())
	if d <= 0 {
		t.Errorf("expected positive jitter delay")
	}
	if injector.GetTotalInjections() != 1 {
		t.Errorf("expected 1 injection, got %d", injector.GetTotalInjections())
	}
}

func TestChassisTamperGuard(t *testing.T) {
	logger, _ := zap.NewDevelopment()
	dmiDir := t.TempDir()
	_ = os.WriteFile(filepath.Join(dmiDir, "chassis_state"), []byte("3\n"), 0644)

	guard := NewChassisTamperGuard(logger, dmiDir, "")
	status, err := guard.AuditChassisState(context.Background())
	if err != nil {
		t.Fatalf("AuditChassisState failed: %v", err)
	}
	if status.ChassisOpened {
		t.Errorf("expected chassis not opened for state 3")
	}
}
