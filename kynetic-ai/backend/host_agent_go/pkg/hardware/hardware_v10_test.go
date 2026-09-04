package hardware

import (
	"context"
	"os"
	"path/filepath"
	"testing"

	"go.uber.org/zap"
)

func TestVBIOSGuard(t *testing.T) {
	logger, _ := zap.NewDevelopment()
	tempDir := t.TempDir()

	// Mock PCI device
	pciDev := filepath.Join(tempDir, "0000:01:00.0")
	_ = os.MkdirAll(pciDev, 0755)
	_ = os.WriteFile(filepath.Join(pciDev, "class"), []byte("0x030000\n"), 0644)
	romFile := filepath.Join(pciDev, "rom")
	_ = os.WriteFile(romFile, []byte{0x55, 0xAA}, 0666)

	guard := NewVBIOSGuard(logger, tempDir)
	locked, err := guard.InspectAndLockVBIOS(context.Background())
	if err != nil {
		t.Fatalf("InspectAndLockVBIOS failed: %v", err)
	}

	if len(locked) != 1 || locked[0] != "0000:01:00.0" {
		t.Errorf("expected 1 locked card, got %v", locked)
	}

	devices := guard.GetLockedDevices()
	if len(devices) != 1 {
		t.Errorf("expected 1 locked device in cache, got %d", len(devices))
	}
}

func TestAudioAirgapManager(t *testing.T) {
	logger, _ := zap.NewDevelopment()
	sndDir := t.TempDir()
	vidDir := t.TempDir()

	_ = os.WriteFile(filepath.Join(sndDir, "pcmC0D0p"), []byte("mock audio"), 0660)
	_ = os.WriteFile(filepath.Join(vidDir, "video0"), []byte("mock camera"), 0660)

	manager := NewAudioAirgapManager(logger, sndDir, vidDir)

	isolated, err := manager.EnforceAirgap(context.Background())
	if err != nil {
		t.Fatalf("EnforceAirgap failed: %v", err)
	}
	if len(isolated) < 2 {
		t.Errorf("expected at least 2 nodes isolated, got %d", len(isolated))
	}
	if !manager.IsAirgapped() {
		t.Errorf("expected IsAirgapped == true")
	}

	err = manager.RestoreAirgap(context.Background())
	if err != nil {
		t.Fatalf("RestoreAirgap failed: %v", err)
	}
	if manager.IsAirgapped() {
		t.Errorf("expected IsAirgapped == false")
	}
}

func TestRowhammerGuard(t *testing.T) {
	logger, _ := zap.NewDevelopment()
	edacDir := t.TempDir()

	mc0 := filepath.Join(edacDir, "mc0")
	_ = os.MkdirAll(mc0, 0755)
	_ = os.WriteFile(filepath.Join(mc0, "ce_count"), []byte("15\n"), 0644)
	_ = os.WriteFile(filepath.Join(mc0, "ue_count"), []byte("0\n"), 0644)

	guard := NewRowhammerGuard(logger, edacDir, 10)
	status, err := guard.ScanEDACControllers(context.Background())
	if err != nil {
		t.Fatalf("ScanEDACControllers failed: %v", err)
	}

	if !status.EDACAvailable {
		t.Errorf("expected EDACAvailable == true")
	}
	if status.CorrectableErrors != 15 {
		t.Errorf("expected 15 CE errors, got %d", status.CorrectableErrors)
	}
	if !status.AnomalyDetected {
		t.Errorf("expected bitflip anomaly to be detected")
	}
}

func TestTelemetryMasker(t *testing.T) {
	logger, _ := zap.NewDevelopment()
	masker := NewTelemetryMasker(logger, 0.05)

	res := masker.FuzzTelemetry(context.Background(), 70.0, 2000, 250.0)
	if !res.IsFuzzed {
		t.Errorf("expected IsFuzzed == true")
	}
	if res.ReportedTempC < 60.0 || res.ReportedTempC > 80.0 {
		t.Errorf("ReportedTempC out of expected jitter range: %f", res.ReportedTempC)
	}
	if res.ReportedFanSpeed < 1800 || res.ReportedFanSpeed > 2200 {
		t.Errorf("ReportedFanSpeed out of expected jitter range: %d", res.ReportedFanSpeed)
	}
}
