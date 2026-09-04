package security

import (
	"testing"
	"time"

	"go.uber.org/zap"
)

func TestDownfallScrubber(t *testing.T) {
	logger := zap.NewNop()
	scrubber := NewDownfallScrubber(logger, "")

	mitigated, status, err := scrubber.AuditDownfallMitigation()
	if err != nil {
		t.Fatalf("AuditDownfallMitigation failed: %v", err)
	}
	if !mitigated || status == "" {
		t.Fatalf("expected Downfall to be mitigated")
	}

	buf := []byte{1, 2, 3, 4, 5}
	scrubber.ScrubVectorRegisters(buf)
	for _, b := range buf {
		if b != 0 {
			t.Fatalf("expected vector buffer to be zeroed")
		}
	}
}

func TestInceptionBarrier(t *testing.T) {
	logger := zap.NewNop()
	barrier := NewInceptionBarrier(logger, "")

	mitigated, _, err := barrier.AuditInceptionMitigation()
	if err != nil || !mitigated {
		t.Fatalf("AuditInceptionMitigation failed: %v", err)
	}
	if err := barrier.IssuePredictionBarrier(); err != nil {
		t.Fatalf("IssuePredictionBarrier failed: %v", err)
	}
}

func TestZenBleedNeutralizer(t *testing.T) {
	logger := zap.NewNop()
	neutralizer := NewZenBleedNeutralizer(logger, "")

	mitigated, _, err := neutralizer.AuditZenBleedMitigation()
	if err != nil || !mitigated {
		t.Fatalf("AuditZenBleedMitigation failed: %v", err)
	}

	raw := []byte{0xDE, 0xAD, 0xBE, 0xEF}
	sanitized := neutralizer.NeutralizeSIMDLeakContext(raw)
	for _, b := range sanitized {
		if b != 0 {
			t.Fatalf("expected sanitized SIMD context to be 0")
		}
	}
}

func TestBHIFlushEngine(t *testing.T) {
	logger := zap.NewNop()
	engine := NewBHIFlushEngine(logger, "")

	mitigated, _, err := engine.AuditBHIMitigation()
	if err != nil || !mitigated {
		t.Fatalf("AuditBHIMitigation failed: %v", err)
	}
	engine.FlushBranchHistoryBuffer()
}

func TestHomomorphicVectorProxy(t *testing.T) {
	proxy := NewHomomorphicVectorProxy(1000.0)
	key := []byte("secret_shared_vector_key_123456")

	v1 := []float64{1.0, 2.0, 3.0}
	v2 := []float64{4.0, 5.0, 6.0}

	enc1, err := proxy.EncryptVector(v1, key)
	if err != nil {
		t.Fatalf("EncryptVector 1 failed: %v", err)
	}
	enc2, err := proxy.EncryptVector(v2, key)
	if err != nil {
		t.Fatalf("EncryptVector 2 failed: %v", err)
	}

	dotProduct, err := proxy.ComputeEncryptedDotProduct(enc1, enc2, key)
	if err != nil {
		t.Fatalf("ComputeEncryptedDotProduct failed: %v", err)
	}

	// 1*4 + 2*5 + 3*6 = 4 + 10 + 18 = 32
	if dotProduct < 31.9 || dotProduct > 32.1 {
		t.Fatalf("expected dot product ~32.0, got %f", dotProduct)
	}
}

func TestMPCThresholdSigner(t *testing.T) {
	shares, err := GenerateDistributedKeyShares(3)
	if err != nil {
		t.Fatalf("GenerateDistributedKeyShares failed: %v", err)
	}

	signer1, _ := NewMPCThresholdSigner(2, 3, 1, shares[0])
	signer2, _ := NewMPCThresholdSigner(2, 3, 2, shares[1])

	msg := []byte("critical_cluster_control_payload")
	p1, err := signer1.GeneratePartialSignature(msg)
	if err != nil {
		t.Fatalf("GeneratePartialSignature p1 failed: %v", err)
	}
	p2, err := signer2.GeneratePartialSignature(msg)
	if err != nil {
		t.Fatalf("GeneratePartialSignature p2 failed: %v", err)
	}

	aggSig, err := signer1.AggregateThresholdSignatures(msg, []*MPCPartialSignature{p1, p2})
	if err != nil {
		t.Fatalf("AggregateThresholdSignatures failed: %v", err)
	}
	if len(aggSig) != 32 {
		t.Fatalf("expected 32-byte aggregated signature")
	}
}

func TestORAMConcealer(t *testing.T) {
	oram := NewORAMConcealer(16, 32)

	err := oram.WriteBlock(42, []byte("sensitive_ai_secret_data"))
	if err != nil {
		t.Fatalf("WriteBlock failed: %v", err)
	}

	data, err := oram.ReadBlock(42)
	if err != nil {
		t.Fatalf("ReadBlock failed: %v", err)
	}
	if string(data[:24]) != "sensitive_ai_secret_data" {
		t.Fatalf("unexpected read data: %s", string(data))
	}
}

func TestQuantumEntropyHarvester(t *testing.T) {
	harvester := NewQuantumEntropyHarvester()

	entropy, err := harvester.HarvestConditionedEntropy(32)
	if err != nil {
		t.Fatalf("HarvestConditionedEntropy failed: %v", err)
	}
	if len(entropy) != 32 {
		t.Fatalf("expected 32 bytes of entropy")
	}

	status := harvester.GetHealthStatus()
	if !status.RepetitionCountPassed || !status.AdaptivePropPassed {
		t.Fatalf("NIST SP 800-90B health tests failed")
	}
}

func TestMemFDSealer(t *testing.T) {
	logger := zap.NewNop()
	sealer := NewMemFDSealer(logger)

	sealed, err := sealer.CreateAndSealAnonymousBuffer("exec_worker_module", []byte("ELF_HEADER_AND_CODE"))
	if err != nil {
		t.Fatalf("CreateAndSealAnonymousBuffer failed: %v", err)
	}
	if !sealed.IsSealed || !sealed.WxSafe {
		t.Fatalf("expected sealed memfd to be W^X safe")
	}

	ok, err := sealer.VerifySeals("exec_worker_module")
	if err != nil || !ok {
		t.Fatalf("VerifySeals failed: %v", err)
	}

	_ = sealer.CleanupSealedBuffer("exec_worker_module")
}

func TestLandlockSandbox(t *testing.T) {
	logger := zap.NewNop()
	sandbox := NewLandlockSandbox(logger, "")

	supported, err := sandbox.AuditLandlockSupport()
	if err != nil || !supported {
		t.Fatalf("AuditLandlockSupport failed: %v", err)
	}

	rules, err := sandbox.ApplySandboxingRuleset("tenant-abc", []string{"/app/read"}, []string{"/app/write"}, []string{"/app/bin"})
	if err != nil || !rules.RulesetActive {
		t.Fatalf("ApplySandboxingRuleset failed: %v", err)
	}

	if !sandbox.IsPathPermitted("tenant-abc", "/app/read/file.txt", false) {
		t.Fatalf("expected /app/read/file.txt to be permitted for read")
	}
	if sandbox.IsPathPermitted("tenant-abc", "/etc/shadow", true) {
		t.Fatalf("expected /etc/shadow to be blocked for write")
	}
}

func TestFGKASLRAuditor(t *testing.T) {
	logger := zap.NewNop()
	auditor := NewFGKASLRAuditor(logger, "")

	status, err := auditor.AuditFGKASLR()
	if err != nil {
		t.Fatalf("AuditFGKASLR failed: %v", err)
	}
	if !status.KASLREnabled {
		t.Fatalf("expected KASLR to be enabled")
	}
}

func TestPIDDepletionGuard(t *testing.T) {
	logger := zap.NewNop()
	guard := NewPIDDepletionGuard(logger, "", 50*time.Millisecond)

	pidMax, isSafe, err := guard.AuditPIDCapacity()
	if err != nil || !isSafe || pidMax < 65536 {
		t.Fatalf("AuditPIDCapacity failed: %v", err)
	}

	guard.MarkTerminatedPID(9999)
	if !guard.IsPIDQuarantined(9999) {
		t.Fatalf("PID 9999 should be quarantined immediately after termination")
	}

	time.Sleep(60 * time.Millisecond)
	if guard.IsPIDQuarantined(9999) {
		t.Fatalf("PID 9999 should exit quarantine after cooldown")
	}
}

func TestModelWatermarkVerifier(t *testing.T) {
	verifier, err := NewModelWatermarkVerifier([]byte("secret_model_author_key"), 0.8)
	if err != nil {
		t.Fatalf("NewModelWatermarkVerifier failed: %v", err)
	}

	weights := make([]float64, 100)
	for i := range weights {
		weights[i] = 0.5
	}

	watermarked := verifier.EmbedWatermark(weights, 0.05)
	verified, corr := verifier.VerifyWatermark(watermarked)
	if !verified || corr < 0.8 {
		t.Fatalf("expected watermark to verify with high correlation, got corr=%f", corr)
	}
}

func TestDifferentialPrivacyShield(t *testing.T) {
	shield := NewDifferentialPrivacyShield(1.0, 1e-5, 1.0)

	grads := []float64{3.0, 4.0} // norm = 5.0
	clipped := shield.ClipGradients(grads)
	// After clipping to norm 1.0 -> [0.6, 0.8]
	if clipped[0] > 0.61 || clipped[0] < 0.59 {
		t.Fatalf("unexpected clipped gradient: %f", clipped[0])
	}

	logits := []float64{10.0, 2.0, -1.0}
	sanitized := shield.SanitizeLogits(logits)
	if len(sanitized) != 3 {
		t.Fatalf("expected 3 sanitized logits")
	}
}

func TestFGSMPurifier(t *testing.T) {
	purifier := NewFGSMPurifier(1, 5)

	cleanSignal := []float64{0.5, 0.5, 0.5, 0.5, 0.5}
	noisySignal := []float64{0.0, 1.0, 0.0, 1.0, 0.0}

	isAdv, _ := purifier.DetectAdversarialNoise(cleanSignal)
	if isAdv {
		t.Fatalf("clean signal should not be flagged adversarial")
	}

	isAdv, _ = purifier.DetectAdversarialNoise(noisySignal)
	if !isAdv {
		t.Fatalf("high-frequency noisy signal should be flagged adversarial")
	}

	purified := purifier.PurifyInputTensor(noisySignal)
	if len(purified) != len(noisySignal) {
		t.Fatalf("unexpected purified tensor length")
	}
}
