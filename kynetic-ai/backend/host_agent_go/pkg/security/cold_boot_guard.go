package security

import (
	"crypto/rand"
	"sync"

	"go.uber.org/zap"
)

// ColdBootGuard ensures volatile memory buffers containing encryption keys or tenant credentials
// are immediately zeroized / overwritten with cryptographic random noise on teardown or panic.
type ColdBootGuard struct {
	logger        *zap.Logger
	mu            sync.Mutex
	purgedBuffers int
}

// NewColdBootGuard creates a new ColdBootGuard.
func NewColdBootGuard(logger *zap.Logger) *ColdBootGuard {
	return &ColdBootGuard{
		logger: logger,
	}
}

// PurgeKeyBuffer overwrites the buffer with random bytes then zeros it out to defeat DRAM remanence.
func (c *ColdBootGuard) PurgeKeyBuffer(buf []byte) {
	c.mu.Lock()
	defer c.mu.Unlock()

	if len(buf) == 0 {
		return
	}

	// 1. Fill with random noise
	_, _ = rand.Read(buf)

	// 2. Overwrite with zeroes
	for i := range buf {
		buf[i] = 0
	}

	c.purgedBuffers++
	c.logger.Debug("Volatile key buffer purged against cold-boot attacks", zap.Int("len", len(buf)))
}

// GetPurgedCount returns count of purged buffers.
func (c *ColdBootGuard) GetPurgedCount() int {
	c.mu.Lock()
	defer c.mu.Unlock()
	return c.purgedBuffers
}
