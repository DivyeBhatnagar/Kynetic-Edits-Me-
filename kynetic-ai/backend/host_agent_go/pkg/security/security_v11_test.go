package security

import (
	"context"
	"os"
	"path/filepath"
	"testing"

	"go.uber.org/zap"
)

func TestMemoryPoisonShield(t *testing.T) {
	logger, _ := zap.NewDevelopment()
	shield := NewMemoryPoisonShield(logger)

	buf := []byte("confidential-aes-encryption-key-data")
	err := shield.ProtectBuffer(context.Background(), buf)
	if err != nil {
		t.Fatalf("ProtectBuffer failed: %v", err)
	}

	if shield.GetLockedBuffersCount() != 1 {
		t.Errorf("expected 1 locked buffer, got %d", shield.GetLockedBuffersCount())
	}
}

func TestColdBootGuard(t *testing.T) {
	logger, _ := zap.NewDevelopment()
	guard := NewColdBootGuard(logger)

	buf := []byte("super-secret-tpm-sealed-seed-bytes")
	guard.PurgeKeyBuffer(buf)

	for i, b := range buf {
		if b != 0 {
			t.Errorf("byte at index %d not zeroized, got %d", i, b)
		}
	}
	if guard.GetPurgedCount() != 1 {
		t.Errorf("expected 1 purged buffer, got %d", guard.GetPurgedCount())
	}
}

func TestShadowStackController(t *testing.T) {
	logger, _ := zap.NewDevelopment()
	cpuFile := filepath.Join(t.TempDir(), "cpuinfo")
	_ = os.WriteFile(cpuFile, []byte("flags: fpu vme de pse tsc msr pae mce cx8 apic shstk ibt\n"), 0644)

	ctrl := NewShadowStackController(logger, cpuFile)
	status, err := ctrl.AuditShadowStackFeatures(context.Background())
	if err != nil {
		t.Fatalf("AuditShadowStackFeatures failed: %v", err)
	}
	if !status.CETSupported || !status.IBTActive {
		t.Errorf("expected CET and IBT active, got %+v", status)
	}
}

func TestBPFRestrictor(t *testing.T) {
	logger, _ := zap.NewDevelopment()
	procSys := t.TempDir()

	_ = os.MkdirAll(filepath.Join(procSys, "kernel"), 0755)
	_ = os.MkdirAll(filepath.Join(procSys, "net", "core"), 0755)

	_ = os.WriteFile(filepath.Join(procSys, "kernel", "unprivileged_bpf_disabled"), []byte("0\n"), 0644)
	_ = os.WriteFile(filepath.Join(procSys, "net", "core", "bpf_jit_harden"), []byte("0\n"), 0644)

	restrictor := NewBPFRestrictor(logger, procSys)
	err := restrictor.ApplyBPFHardening(context.Background())
	if err != nil {
		t.Fatalf("ApplyBPFHardening failed: %v", err)
	}

	if !restrictor.IsHardened() {
		t.Errorf("expected IsHardened == true")
	}
}

func TestRegisterZeroingInspector(t *testing.T) {
	logger, _ := zap.NewDevelopment()
	inspector := NewRegisterZeroingInspector(logger)

	a := []byte("secret-token-12345")
	b := []byte("secret-token-12345")
	c := []byte("secret-token-wrong")

	if !inspector.ConstantTimeCompare(a, b) {
		t.Errorf("expected a and b to match in constant time")
	}
	if inspector.ConstantTimeCompare(a, c) {
		t.Errorf("expected a and c not to match")
	}

	inspector.ScrubMemory(a)
	for _, byteVal := range a {
		if byteVal != 0 {
			t.Errorf("expected memory to be wiped to zero")
		}
	}
}

func TestModuleSigningGuard(t *testing.T) {
	logger, _ := zap.NewDevelopment()
	sysDir := t.TempDir()
	_ = os.WriteFile(filepath.Join(sysDir, "sig_enforce"), []byte("Y\n"), 0644)

	guard := NewModuleSigningGuard(logger, sysDir)
	enforced, err := guard.AuditModuleSigning(context.Background())
	if err != nil {
		t.Fatalf("AuditModuleSigning failed: %v", err)
	}
	if !enforced || !guard.IsEnforced() {
		t.Errorf("expected module signing to be enforced")
	}
}

func TestHomomorphicHeartbeatEngine(t *testing.T) {
	logger, _ := zap.NewDevelopment()
	engine := NewHomomorphicHeartbeatEngine(logger, []byte("node-signing-seed-0123456789"))

	state := []byte("host-healthy-gpu-idle-score-100")
	hb := engine.GenerateHeartbeat(context.Background(), "host-node-99", state)

	if hb.HostID != "host-node-99" || hb.Sequence != 1 || hb.BlindedProof == "" {
		t.Errorf("invalid heartbeat payload: %+v", hb)
	}
}
