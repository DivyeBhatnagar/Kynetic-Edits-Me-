package security

import (
	"context"
	"os"
	"path/filepath"
	"testing"

	"go.uber.org/zap"
)

func TestSpeculationBarrierManager(t *testing.T) {
	logger, _ := zap.NewDevelopment()
	mgr := NewSpeculationBarrierManager(logger)

	err := mgr.EnforceSpeculationBarrier(context.Background())
	if err != nil {
		t.Fatalf("EnforceSpeculationBarrier failed: %v", err)
	}
	if !mgr.IsBarrierActive() {
		t.Errorf("expected barrier active")
	}
}

func TestL1TFScrubber(t *testing.T) {
	logger, _ := zap.NewDevelopment()
	tempDir := t.TempDir()
	_ = os.WriteFile(filepath.Join(tempDir, "l1tf"), []byte("Mitigation: PTE Inversion; VMX: cache flushes, SMT disabled\n"), 0644)

	scrubber := NewL1TFScrubber(logger, tempDir)
	mitigated, _, err := scrubber.AuditL1TFMitigation(context.Background())
	if err != nil {
		t.Fatalf("AuditL1TFMitigation failed: %v", err)
	}
	if !mitigated {
		t.Errorf("expected L1TF to be mitigated")
	}
	scrubber.TriggerFlush()
	if scrubber.GetFlushCount() != 1 {
		t.Errorf("expected 1 flush count, got %d", scrubber.GetFlushCount())
	}
}

func TestMDSBufferClearer(t *testing.T) {
	logger, _ := zap.NewDevelopment()
	tempDir := t.TempDir()
	_ = os.WriteFile(filepath.Join(tempDir, "mds"), []byte("Mitigation: Clear CPU buffers; SMT disabled\n"), 0644)

	clearer := NewMDSBufferClearer(logger, tempDir)
	mitigated, _, err := clearer.AuditMDSMitigation(context.Background())
	if err != nil {
		t.Fatalf("AuditMDSMitigation failed: %v", err)
	}
	if !mitigated {
		t.Errorf("expected MDS to be mitigated")
	}
	clearer.RecordBufferClear()
	if clearer.GetClearedRuns() != 1 {
		t.Errorf("expected 1 cleared run, got %d", clearer.GetClearedRuns())
	}
}

func TestTLBIsolationManager(t *testing.T) {
	logger, _ := zap.NewDevelopment()
	tempDir := t.TempDir()
	_ = os.WriteFile(filepath.Join(tempDir, "meltdown"), []byte("Mitigation: PTI\n"), 0644)

	mgr := NewTLBIsolationManager(logger, tempDir)
	active, _, err := mgr.AuditKPTIStatus(context.Background())
	if err != nil {
		t.Fatalf("AuditKPTIStatus failed: %v", err)
	}
	if !active || !mgr.IsKPTIActive() {
		t.Errorf("expected KPTI to be active")
	}
}

func TestPQCKEMEngine(t *testing.T) {
	logger, _ := zap.NewDevelopment()
	engine := NewPQCKEMEngine(logger)

	peerSeed := []byte("peer-x25519-public-key-seed-32bytes")
	res, err := engine.EncapsulateSecret(context.Background(), peerSeed)
	if err != nil {
		t.Fatalf("EncapsulateSecret failed: %v", err)
	}
	if len(res.SharedSecret) != 32 || len(res.Ciphertext) == 0 {
		t.Errorf("invalid PQC encapsulation result: %+v", res)
	}
	if engine.GetEncapCount() != 1 {
		t.Errorf("expected 1 encap count, got %d", engine.GetEncapCount())
	}
}

func TestPQCSignatureEngine(t *testing.T) {
	logger, _ := zap.NewDevelopment()
	engine := NewPQCSignatureEngine(logger)

	msg := []byte("kynetic-host-tpm-quote-measurement-vector")
	privKey := []byte("pqc-private-key-seed-material-512bit")

	sigHex, err := engine.SignPayload(context.Background(), msg, privKey)
	if err != nil {
		t.Fatalf("SignPayload failed: %v", err)
	}

	valid := engine.VerifySignature(context.Background(), msg, sigHex, privKey)
	if !valid {
		t.Errorf("expected signature to verify successfully")
	}

	tamperedValid := engine.VerifySignature(context.Background(), []byte("tampered message"), sigHex, privKey)
	if tamperedValid {
		t.Errorf("expected tampered message verification to fail")
	}
}

func TestShamirSecretManager(t *testing.T) {
	logger, _ := zap.NewDevelopment()
	mgr := NewShamirSecretManager(logger)

	secret := []byte("host-luks2-master-encryption-key-512bits-long-payload")
	shards, err := mgr.Split2of3(context.Background(), secret)
	if err != nil {
		t.Fatalf("Split2of3 failed: %v", err)
	}
	if len(shards) != 3 {
		t.Fatalf("expected 3 shards, got %d", len(shards))
	}

	reconstructed, err := mgr.Reconstruct3of3(shards)
	if err != nil {
		t.Fatalf("Reconstruct3of3 failed: %v", err)
	}
	if string(reconstructed) != string(secret) {
		t.Errorf("expected '%s', got '%s'", string(secret), string(reconstructed))
	}
}

func TestZKPInferenceEngine(t *testing.T) {
	logger, _ := zap.NewDevelopment()
	engine := NewZKPInferenceEngine(logger)

	modelID := "meta-llama/Llama-3-70B-Instruct"
	prompt := []byte("Explain quantum entanglement in simple terms.")
	output := []byte("Quantum entanglement is a physical phenomenon...")

	proof := engine.GenerateProof(context.Background(), modelID, prompt, output)
	if !engine.VerifyProof(context.Background(), proof) {
		t.Errorf("expected valid ZKP inference proof to verify")
	}

	// Tampered output verification check
	proof.OutputCommitment = "deadbeef12345678"
	if engine.VerifyProof(context.Background(), proof) {
		t.Errorf("expected tampered ZKP proof to fail verification")
	}
}

func TestNestedVirtLockout(t *testing.T) {
	logger, _ := zap.NewDevelopment()
	tempDir := t.TempDir()

	intelNested := filepath.Join(tempDir, "kvm_intel", "parameters")
	_ = os.MkdirAll(intelNested, 0755)
	_ = os.WriteFile(filepath.Join(intelNested, "nested"), []byte("N\n"), 0644)

	lock := NewNestedVirtLockout(logger, tempDir)
	disabled, err := lock.AuditAndDisableNestedVirt(context.Background())
	if err != nil {
		t.Fatalf("AuditAndDisableNestedVirt failed: %v", err)
	}
	if !disabled || !lock.IsLocked() {
		t.Errorf("expected nested virt locked")
	}
}

func TestHostInfoRedactor(t *testing.T) {
	logger, _ := zap.NewDevelopment()
	redactor := NewHostInfoRedactor(logger)

	rawLog := "Host detected at MAC 00:1A:2B:3C:4D:5E with Machine UUID 550e8400-e29b-41d4-a716-446655440000 System Serial Number 12345"
	cleanLog := redactor.RedactString(rawLog)

	if redactor.GetRedactedCount() < 2 {
		t.Errorf("expected at least 2 identifiers redacted, got %d", redactor.GetRedactedCount())
	}
	if !redactor.macRegex.MatchString("00:1A:2B:3C:4D:5E") {
		t.Errorf("regex should match raw mac")
	}
	if cleanLog == rawLog {
		t.Errorf("expected redacted log to differ from raw log")
	}
}

func TestUserNamespaceJail(t *testing.T) {
	logger, _ := zap.NewDevelopment()
	procDir := t.TempDir()

	pidDir := filepath.Join(procDir, "1234")
	_ = os.MkdirAll(pidDir, 0755)
	_ = os.WriteFile(filepath.Join(pidDir, "uid_map"), []byte(""), 0644)

	jail := NewUserNamespaceJail(logger, procDir)
	cfg := UserNamespaceConfig{
		ContainerUID: 0,
		HostUIDStart: 100000,
		RangeCount:   65536,
	}

	err := jail.ConfigureUIDMap(context.Background(), 1234, cfg)
	if err != nil {
		t.Fatalf("ConfigureUIDMap failed: %v", err)
	}
	if jail.GetActiveJails() != 1 {
		t.Errorf("expected 1 active jail, got %d", jail.GetActiveJails())
	}
}
