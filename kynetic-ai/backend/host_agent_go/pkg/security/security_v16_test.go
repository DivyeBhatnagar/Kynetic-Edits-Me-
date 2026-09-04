package security

import (
	"testing"
)

func TestEBPFSyscallCFI(t *testing.T) {
	cfi := NewEBPFSyscallCFI()
	cfi.RegisterPolicy(SyscallCFIPolicy{
		SyscallNumber:    59, // execve
		AllowedCodeBase:  0x400000,
		AllowedCodeLimit: 0x500000,
	})

	// Valid caller IP
	ok, _ := cfi.EvaluateSyscallCaller(59, 0x450000)
	if !ok {
		t.Fatalf("valid caller IP rejected")
	}

	// ROP gadget attack (caller IP in heap/stack 0x7fffffffe000)
	okBad, msgBad := cfi.EvaluateSyscallCaller(59, 0x7fffffffe000)
	if okBad {
		t.Fatalf("ROP gadget execution allowed: %s", msgBad)
	}
}

func TestPKUMPKSandbox(t *testing.T) {
	sandbox := NewPKUMPKSandbox()
	err := sandbox.AllocateDomain(1, "crypto_keys_domain", PKUAccessReadOnly)
	if err != nil {
		t.Fatalf("failed to allocate PKU domain: %v", err)
	}

	// Read is allowed
	okRead, _ := sandbox.AssertAccessPermission(1, false)
	if !okRead {
		t.Fatalf("read to read-only domain should be permitted")
	}

	// Write is blocked
	okWrite, msgWrite := sandbox.AssertAccessPermission(1, true)
	if okWrite {
		t.Fatalf("write to read-only PKU domain allowed: %s", msgWrite)
	}
}

func TestDKMSHashChainAuditor(t *testing.T) {
	auditor := NewDKMSHashChainAuditor()
	auditor.RecordBuildStage("nvidia-peermem", "source_verification", "sha_src_1", "sha_out_1")
	auditor.RecordBuildStage("nvidia-peermem", "compilation", "sha_src_2", "sha_out_2")

	ok, msg := auditor.VerifyChainIntegrity()
	if !ok {
		t.Fatalf("valid DKMS chain failed: %s", msg)
	}
}

func TestRedfishBlackboxLogger(t *testing.T) {
	logger := NewRedfishBlackboxLogger("https://bmc.internal/redfish/v1")
	rec := logger.CapturePanicTelemetry("KERNEL_PAGE_FAULT_IN_NONPAGED_AREA", map[string]string{
		"RIP": "0xffffffff8100234a",
		"CR2": "0x0000000000000000",
	})
	if rec == nil || logger.GetLogCount() != 1 {
		t.Fatalf("failed to capture blackbox telemetry")
	}
}

func TestSeccompUserNotifSupervisor(t *testing.T) {
	supervisor := NewSeccompUserNotifSupervisor()
	supervisor.BlockSyscall(321) // bpf syscall

	// Allowed syscall
	respAllow := supervisor.HandleNotification(SeccompNotifRequest{
		ID:         1,
		PID:        1000,
		SyscallNum: 1, // write
	})
	if !respAllow.Allowed {
		t.Fatalf("benign syscall blocked")
	}

	// Blocked syscall
	respBlock := supervisor.HandleNotification(SeccompNotifRequest{
		ID:         2,
		PID:        1000,
		SyscallNum: 321,
	})
	if respBlock.Allowed {
		t.Fatalf("blacklisted syscall allowed")
	}
}
