package firewall

import (
	"context"
	"sync"

	"go.uber.org/zap"
)

// RapidResetStatus represents client stream reset frequency.
type RapidResetStatus struct {
	ClientIP          string `json:"client_ip"`
	ResetCount        uint32 `json:"reset_count"`
	IsRateLimited     bool   `json:"is_rate_limited"`
	ActionTaken       string `json:"action_taken"`
}

// RapidResetMitigator monitors HTTP/2 and HTTP/3 stream cancellation frames (`RST_STREAM`)
// in real-time to neutralize Layer 7 Rapid Reset DDoS attacks (CVE-2023-44487).
type RapidResetMitigator struct {
	logger           *zap.Logger
	maxResetsPerSec  uint32
	clientResetMap   map[string]uint32
	mu               sync.Mutex
	blockedAttackers uint64
}

// NewRapidResetMitigator creates a new RapidResetMitigator.
func NewRapidResetMitigator(logger *zap.Logger, maxResetsPerSec uint32) *RapidResetMitigator {
	if maxResetsPerSec == 0 {
		maxResetsPerSec = 100 // 100 RST_STREAM frames/sec threshold
	}
	return &RapidResetMitigator{
		logger:          logger,
		maxResetsPerSec: maxResetsPerSec,
		clientResetMap:  make(map[string]uint32),
	}
}

// RecordStreamReset registers a stream reset from a client IP and returns whether the connection must be dropped.
func (r *RapidResetMitigator) RecordStreamReset(ctx context.Context, clientIP string) RapidResetStatus {
	r.mu.Lock()
	defer r.mu.Unlock()

	r.clientResetMap[clientIP]++
	count := r.clientResetMap[clientIP]

	isLimited := false
	action := "allow"

	if count > r.maxResetsPerSec {
		isLimited = true
		action = "drop_connection"
		r.blockedAttackers++
		r.logger.Warn("RapidResetMitigator: HTTP/2 Rapid Reset flood detected (CVE-2023-44487)!",
			zap.String("client_ip", clientIP),
			zap.Uint32("resets_sec", count),
		)
	}

	return RapidResetStatus{
		ClientIP:      clientIP,
		ResetCount:    count,
		IsRateLimited: isLimited,
		ActionTaken:   action,
	}
}

// ResetWindow clears the sliding window counters every interval.
func (r *RapidResetMitigator) ResetWindow() {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.clientResetMap = make(map[string]uint32)
}

// GetBlockedCount returns count of blocked Rapid Reset attackers.
func (r *RapidResetMitigator) GetBlockedCount() uint64 {
	r.mu.Lock()
	defer r.mu.Unlock()
	return r.blockedAttackers
}
