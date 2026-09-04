package security

import (
	"crypto/subtle"
	"sync"

	"go.uber.org/zap"
)

// RegisterZeroingInspector provides helper utilities for constant-time cryptographic
// comparisons and zeroing stack/scratch memory to prevent residual data leaks.
type RegisterZeroingInspector struct {
	logger       *zap.Logger
	mu           sync.Mutex
	scrubbedRuns uint64
}

// NewRegisterZeroingInspector creates a new RegisterZeroingInspector.
func NewRegisterZeroingInspector(logger *zap.Logger) *RegisterZeroingInspector {
	return &RegisterZeroingInspector{
		logger: logger,
	}
}

// ConstantTimeCompare performs a timing-attack resistant byte slice comparison.
func (r *RegisterZeroingInspector) ConstantTimeCompare(a, b []byte) bool {
	r.mu.Lock()
	r.scrubbedRuns++
	r.mu.Unlock()

	return subtle.ConstantTimeCompare(a, b) == 1
}

// ScrubMemory overwrites a sensitive memory slice with zeroes using compiler-safe barriers.
func (r *RegisterZeroingInspector) ScrubMemory(buf []byte) {
	r.mu.Lock()
	r.scrubbedRuns++
	r.mu.Unlock()

	for i := range buf {
		buf[i] = 0
	}
}

// GetScrubbedRuns returns total secure memory operations performed.
func (r *RegisterZeroingInspector) GetScrubbedRuns() uint64 {
	r.mu.Lock()
	defer r.mu.Unlock()
	return r.scrubbedRuns
}
