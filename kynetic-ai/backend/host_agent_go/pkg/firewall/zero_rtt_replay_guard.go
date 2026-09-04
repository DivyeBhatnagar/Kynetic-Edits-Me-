package firewall

import (
	"crypto/sha256"
	"fmt"
	"sync"
	"time"

	"go.uber.org/zap"
)

// ZeroRTTReplayGuard implements a cryptographically hashed sliding-window cache to detect and drop
// replayed 0-RTT early data packets in TLS 1.3 and QUIC connections.
type ZeroRTTReplayGuard struct {
	logger        *zap.Logger
	windowSize    time.Duration
	mu            sync.Mutex
	seenTickets   map[[32]byte]time.Time
}

// NewZeroRTTReplayGuard creates a new 0-RTT replay cache.
func NewZeroRTTReplayGuard(logger *zap.Logger, windowSize time.Duration) *ZeroRTTReplayGuard {
	if windowSize <= 0 {
		windowSize = 10 * time.Second
	}
	return &ZeroRTTReplayGuard{
		logger:      logger,
		windowSize:  windowSize,
		seenTickets: make(map[[32]byte]time.Time),
	}
}

// ValidateEarlyDataTicket verifies that an early-data resumption ticket has not been previously observed within the time window.
func (g *ZeroRTTReplayGuard) ValidateEarlyDataTicket(ticketID []byte, clientTimestamp time.Time) (bool, error) {
	g.mu.Lock()
	defer g.mu.Unlock()

	now := time.Now()
	// Check if ticket timestamp is outside sliding window
	if now.Sub(clientTimestamp) > g.windowSize || clientTimestamp.Sub(now) > g.windowSize {
		return false, fmt.Errorf("0-RTT ticket timestamp outside acceptable sliding window")
	}

	hash := sha256.Sum256(ticketID)
	if _, exists := g.seenTickets[hash]; exists {
		g.logger.Warn("ZeroRTTReplayGuard: Replay attack detected! Duplicate 0-RTT early data ticket dropped",
			zap.String("ticket_hash", fmt.Sprintf("%x", hash[:8])),
		)
		return false, fmt.Errorf("0-RTT replay attack detected")
	}

	// Purge stale tickets
	cutoff := now.Add(-g.windowSize)
	for h, ts := range g.seenTickets {
		if ts.Before(cutoff) {
			delete(g.seenTickets, h)
		}
	}

	g.seenTickets[hash] = clientTimestamp
	return true, nil
}
