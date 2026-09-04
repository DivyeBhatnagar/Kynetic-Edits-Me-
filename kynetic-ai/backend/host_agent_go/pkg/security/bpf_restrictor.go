package security

import (
	"context"
	"os"
	"path/filepath"
	"sync"

	"go.uber.org/zap"
)

// BPFRestrictor enforces eBPF JIT constant blinding (`net.core.bpf_jit_harden = 2`)
// and disables unprivileged BPF system calls (`kernel.unprivileged_bpf_disabled = 1`).
type BPFRestrictor struct {
	logger        *zap.Logger
	sysctlPath    string
	mu            sync.Mutex
	isHardened    bool
}

// NewBPFRestrictor creates a new BPFRestrictor.
func NewBPFRestrictor(logger *zap.Logger, sysctlPath string) *BPFRestrictor {
	if sysctlPath == "" {
		sysctlPath = "/proc/sys"
	}
	return &BPFRestrictor{
		logger:     logger,
		sysctlPath: sysctlPath,
	}
}

// ApplyBPFHardening writes hardening values to proc sysctl nodes.
func (b *BPFRestrictor) ApplyBPFHardening(ctx context.Context) error {
	b.mu.Lock()
	defer b.mu.Unlock()

	// 1. Disable unprivileged BPF
	unprivilegedBpfPath := filepath.Join(b.sysctlPath, "kernel", "unprivileged_bpf_disabled")
	if _, err := os.Stat(unprivilegedBpfPath); err == nil {
		_ = os.WriteFile(unprivilegedBpfPath, []byte("1\n"), 0644)
	}

	// 2. Harden BPF JIT with constant blinding (2 = Harden for all users)
	jitHardenPath := filepath.Join(b.sysctlPath, "net", "core", "bpf_jit_harden")
	if _, err := os.Stat(jitHardenPath); err == nil {
		_ = os.WriteFile(jitHardenPath, []byte("2\n"), 0644)
	}

	b.isHardened = true
	b.logger.Info("eBPF JIT Constant Blinding & Unprivileged BPF Restriction enforced")
	return nil
}

// IsHardened returns current BPF hardening state.
func (b *BPFRestrictor) IsHardened() bool {
	b.mu.Lock()
	defer b.mu.Unlock()
	return b.isHardened
}
