package security

import (
	"context"
	"os"
	"path/filepath"
	"testing"
	"time"

	"go.uber.org/zap"
)

func TestKernelLockdownController(t *testing.T) {
	logger, _ := zap.NewDevelopment()
	tempDir := t.TempDir()
	lockdownFile := filepath.Join(tempDir, "lockdown")
	_ = os.WriteFile(lockdownFile, []byte("none [integrity] confidentiality\n"), 0644)

	ctrl := NewKernelLockdownController(logger, lockdownFile)
	level, err := ctrl.QueryCurrentLockdown()
	if err != nil {
		t.Fatalf("QueryCurrentLockdown failed: %v", err)
	}
	if level != LockdownIntegrity {
		t.Errorf("expected level to be integrity, got %s", level)
	}

	err = ctrl.EnforceConfidentialityMode(context.Background(), LockdownConfidential)
	if err != nil {
		t.Fatalf("EnforceConfidentialityMode failed: %v", err)
	}
	if ctrl.GetLevel() != LockdownConfidential {
		t.Errorf("expected level to be confidentiality, got %s", ctrl.GetLevel())
	}
}

func TestHardwareWatchdog(t *testing.T) {
	logger, _ := zap.NewDevelopment()
	tempDev := filepath.Join(t.TempDir(), "watchdog")

	wd := NewHardwareWatchdog(logger, tempDev, 50*time.Millisecond)
	err := wd.ArmWatchdog(context.Background())
	if err != nil {
		t.Fatalf("ArmWatchdog failed: %v", err)
	}
	if !wd.IsArmed() {
		t.Errorf("expected watchdog to be armed")
	}

	time.Sleep(100 * time.Millisecond)

	err = wd.DisarmSafely()
	if err != nil {
		t.Fatalf("DisarmSafely failed: %v", err)
	}
	if wd.IsArmed() {
		t.Errorf("expected watchdog to be disarmed")
	}
}

func TestTPMSealedVault(t *testing.T) {
	logger, _ := zap.NewDevelopment()
	vault := NewTPMSealedVault(logger, "/dev/null", 7)

	pcrState := []byte("pcr-state-secure-boot-active-0123456789abcdef")
	secret := []byte("kynetic-host-private-ed25519-key-payload")

	sealed, err := vault.SealSecret(context.Background(), secret, pcrState)
	if err != nil {
		t.Fatalf("SealSecret failed: %v", err)
	}

	// Unseal with matching PCR state
	unsealed, err := vault.UnsealSecret(context.Background(), sealed, pcrState)
	if err != nil {
		t.Fatalf("UnsealSecret failed: %v", err)
	}
	if string(unsealed) != string(secret) {
		t.Errorf("expected secret '%s', got '%s'", string(secret), string(unsealed))
	}

	// Attempt unseal with tampered PCR state
	tamperedPCR := []byte("pcr-state-tampered-firmware-detected-xxx")
	_, err = vault.UnsealSecret(context.Background(), sealed, tamperedPCR)
	if err == nil {
		t.Fatalf("expected UnsealSecret to fail with tampered PCR state")
	}
}

func TestCgroupLimitsManager(t *testing.T) {
	logger, _ := zap.NewDevelopment()
	cgroupRoot := t.TempDir()

	mgr := NewCgroupLimitsManager(logger, cgroupRoot)

	ceiling := CgroupCeiling{
		MaxPids:     256,
		MemoryMaxMB: 2048,
		SwapMaxMB:   0,
	}

	err := mgr.ApplyContainerLimits(context.Background(), "tenant-xyz", ceiling)
	if err != nil {
		t.Fatalf("ApplyContainerLimits failed: %v", err)
	}

	if mgr.GetAppliedPidsLimit("tenant-xyz") != 256 {
		t.Errorf("expected pids limit 256, got %d", mgr.GetAppliedPidsLimit("tenant-xyz"))
	}

	err = mgr.RemoveContainerLimits(context.Background(), "tenant-xyz")
	if err != nil {
		t.Fatalf("RemoveContainerLimits failed: %v", err)
	}
	if mgr.GetAppliedPidsLimit("tenant-xyz") != 0 {
		t.Errorf("expected pids limit 0 after cleanup, got %d", mgr.GetAppliedPidsLimit("tenant-xyz"))
	}
}
