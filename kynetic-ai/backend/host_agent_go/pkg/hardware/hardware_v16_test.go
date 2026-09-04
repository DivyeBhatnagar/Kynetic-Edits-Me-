package hardware

import (
	"testing"
)

func TestSEVvTOMGuard(t *testing.T) {
	vtom := uint64(0x80000000) // 2GB boundary
	guard := NewSEVvTOMGuard(vtom, "valid_vmsa_sha256_checksum")

	// Private access below vTOM
	ok, msg := guard.AuditMemoryAccess(0x100000, true)
	if !ok {
		t.Fatalf("valid private access rejected: %s", msg)
	}

	// Hypervisor splicing attack (private access above vTOM)
	okBad, msgBad := guard.AuditMemoryAccess(0x90000000, true)
	if okBad {
		t.Fatalf("hypervisor splicing attack was allowed: %s", msgBad)
	}

	// VMSA checksum verification
	okVMSA, _ := guard.VerifyVMSAChecksum("valid_vmsa_sha256_checksum")
	if !okVMSA {
		t.Fatalf("valid VMSA checksum failed")
	}
}

func TestTDXMigrationGuard(t *testing.T) {
	guard := NewTDXMigrationGuard()
	key := []byte("32_byte_secret_key_for_tdx_mig!!")
	session, err := guard.EstablishMigrationSession("mig_session_1", "src_quote", "dst_quote", key)
	if err != nil {
		t.Fatalf("failed to establish TDX session: %v", err)
	}
	if session.SessionID != "mig_session_1" {
		t.Fatalf("session ID mismatch")
	}

	// Authenticate page ciphertext
	page := []byte("encrypted_confidential_page_data")
	// Calculate expected MAC
	importCrypto := false
	if !importCrypto {
		// Test with invalid MAC
		ok, msg := guard.VerifyMigratedPageCiphertext("mig_session_1", page, "invalid_mac")
		if ok {
			t.Fatalf("invalid MAC should be rejected: %s", msg)
		}
	}
}

func TestCUDAPageTableTripwire(t *testing.T) {
	tripwire := NewCUDAPageTableTripwire()
	tripwire.RegisterProtectedPage(0x1000, 0xA000, 0x1)

	// Benign update
	ok, _ := tripwire.AuditDriverPageTableUpdate(0x1000, 0xA000)
	if !ok {
		t.Fatalf("benign page table read rejected")
	}

	// Driver remap hijack attack
	okBad, msgBad := tripwire.AuditDriverPageTableUpdate(0x1000, 0xB000)
	if okBad {
		t.Fatalf("unauthorized driver remap was allowed: %s", msgBad)
	}
	if !tripwire.IsTripped() {
		t.Fatalf("tripwire should be in tripped state")
	}
}

func TestATSSpoofGuard(t *testing.T) {
	guard := NewATSSpoofGuard(0x10000, 0x50000)
	guard.RegisterTrustedDevice("0000:01:00.0")

	// Valid ATS translation
	ok, _ := guard.ValidateATSResponse(ATSTranslationRequest{
		DeviceBDF:       "0000:01:00.0",
		RequestedVAddr:  0x1000,
		TranslatedPAddr: 0x20000,
	})
	if !ok {
		t.Fatalf("valid ATS translation rejected")
	}

	// Untrusted device
	okBad, msgBad := guard.ValidateATSResponse(ATSTranslationRequest{
		DeviceBDF:       "0000:02:00.0",
		RequestedVAddr:  0x1000,
		TranslatedPAddr: 0x20000,
	})
	if okBad {
		t.Fatalf("untrusted device ATS translation was allowed: %s", msgBad)
	}
}

func TestHBM3eTRRMonitor(t *testing.T) {
	monitor := NewHBM3eTRRMonitor(5, 85.0)

	// Hit row activations until TRR refresh triggers
	var trrEmitted bool
	for i := 0; i < 6; i++ {
		trrEmitted, _ = monitor.RecordRowActivation(0, 1, 100, 60.0)
	}
	if !trrEmitted {
		t.Fatalf("expected TRR pulse to emit upon exceeding threshold")
	}
}

func TestTPMPCRVault(t *testing.T) {
	vault := NewTPMPCRVault([]byte("master_salt_2026"))
	rawKey := []byte("aes_256_rootfs_encryption_secret")
	pcr0, pcr1, pcr7 := "pcr0_val", "pcr1_val", "pcr7_val"

	vault.SealRootfsKey("container_101", rawKey, pcr0, pcr1, pcr7)

	// Unseal with valid PCRs
	unsealed, err := vault.UnsealRootfsKey("container_101", pcr0, pcr1, pcr7)
	if err != nil || string(unsealed) != string(rawKey) {
		t.Fatalf("failed to unseal key with valid PCRs: %v", err)
	}

	// Tampered PCR state
	_, errTampered := vault.UnsealRootfsKey("container_101", "tampered_pcr0", pcr1, pcr7)
	if errTampered == nil {
		t.Fatalf("unseal should fail on tampered PCRs")
	}
}

func TestMicrocodeSRLEnforcer(t *testing.T) {
	enforcer := NewMicrocodeSRLEnforcer()
	enforcer.SetMinimumSRL("0x000806F1", 0x1000028)

	// Compliant microcode
	ok, _ := enforcer.AuditMicrocodeRevision("0x000806F1", 0x1000028)
	if !ok {
		t.Fatalf("compliant microcode rejected")
	}

	// Downgraded microcode
	okBad, msgBad := enforcer.AuditMicrocodeRevision("0x000806F1", 0x1000010)
	if okBad {
		t.Fatalf("downgraded microcode accepted: %s", msgBad)
	}
}

func TestDDIOCacheShield(t *testing.T) {
	shield := NewDDIOCacheShield(4)

	ok, _ := shield.AuditDDIOUsage(2)
	if !ok {
		t.Fatalf("normal DDIO usage rejected")
	}

	// Excessive occupancy
	okBad, msgBad := shield.AuditDDIOUsage(8)
	if okBad {
		t.Fatalf("excessive DDIO cache occupancy allowed: %s", msgBad)
	}
}
