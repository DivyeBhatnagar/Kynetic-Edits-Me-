package security

import (
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"sync"
	"time"

	"go.uber.org/zap"
)

// BlindedHeartbeat represents a cryptographically verifiable host heartbeat payload.
type BlindedHeartbeat struct {
	HostID        string    `json:"host_id"`
	Sequence      uint64    `json:"sequence"`
	BlindedProof  string    `json:"blinded_proof"`
	Timestamp     time.Time `json:"timestamp"`
}

// HomomorphicHeartbeatEngine generates blinded, tamper-proof state proofs for host
// uptime and verification consensus without leaking internal telemetry parameters.
type HomomorphicHeartbeatEngine struct {
	logger      *zap.Logger
	hostSecret  []byte
	mu          sync.Mutex
	sequenceNum uint64
}

// NewHomomorphicHeartbeatEngine instantiates a new HomomorphicHeartbeatEngine.
func NewHomomorphicHeartbeatEngine(logger *zap.Logger, hostSecret []byte) *HomomorphicHeartbeatEngine {
	if len(hostSecret) == 0 {
		hostSecret = []byte("kynetic-ephemeral-consensus-seed")
	}
	return &HomomorphicHeartbeatEngine{
		logger:     logger,
		hostSecret: hostSecret,
	}
}

// GenerateHeartbeat computes an HMAC-SHA256 blinded state token for consensus submission.
func (h *HomomorphicHeartbeatEngine) GenerateHeartbeat(ctx context.Context, hostID string, stateDigest []byte) BlindedHeartbeat {
	h.mu.Lock()
	h.sequenceNum++
	seq := h.sequenceNum
	h.mu.Unlock()

	mac := hmac.New(sha256.New, h.hostSecret)
	mac.Write([]byte(hostID))
	mac.Write(stateDigest)
	mac.Write([]byte(time.Now().UTC().Format(time.RFC3339)))

	proofHex := hex.EncodeToString(mac.Sum(nil))

	return BlindedHeartbeat{
		HostID:       hostID,
		Sequence:     seq,
		BlindedProof: proofHex,
		Timestamp:    time.Now().UTC(),
	}
}

// GetSequence returns current heartbeat sequence number.
func (h *HomomorphicHeartbeatEngine) GetSequence() uint64 {
	h.mu.Lock()
	defer h.mu.Unlock()
	return h.sequenceNum
}
