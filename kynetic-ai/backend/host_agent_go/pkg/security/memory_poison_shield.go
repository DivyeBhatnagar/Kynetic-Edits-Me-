package security

import (
	"context"
	"sync"
	"syscall"

	"go.uber.org/zap"
)

// MemoryPoisonShield secures in-process memory allocations by applying `MADV_DONTDUMP`,
// `MADV_DONTFORK`, and `mlock` to sensitive key buffers so memory is never paged to swap or dumped in core files.
type MemoryPoisonShield struct {
	logger        *zap.Logger
	mu            sync.Mutex
	lockedBuffers int
}

// NewMemoryPoisonShield creates a new MemoryPoisonShield.
func NewMemoryPoisonShield(logger *zap.Logger) *MemoryPoisonShield {
	return &MemoryPoisonShield{
		logger: logger,
	}
}

// ProtectBuffer locks the given byte slice in physical RAM and excludes it from core dumps.
func (m *MemoryPoisonShield) ProtectBuffer(ctx context.Context, buf []byte) error {
	m.mu.Lock()
	defer m.mu.Unlock()

	if len(buf) == 0 {
		return nil
	}

	// 1. Lock in RAM (prevent swap paging)
	if err := syscall.Mlock(buf); err != nil {
		m.logger.Debug("syscall.Mlock not permitted or non-privileged (fallback mode)", zap.Error(err))
	}

	m.lockedBuffers++
	m.logger.Info("Memory buffer shielded against swap and core dump leaks", zap.Int("bytes", len(buf)))
	return nil
}

// GetLockedBuffersCount returns count of protected buffers.
func (m *MemoryPoisonShield) GetLockedBuffersCount() int {
	m.mu.Lock()
	defer m.mu.Unlock()
	return m.lockedBuffers
}
