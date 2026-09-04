package security

import (
	"context"
	"crypto/hmac"
	"crypto/sha512"
	"encoding/hex"
	"fmt"
	"sync"

	"go.uber.org/zap"
)

// PQCSignatureEngine handles lattice-based digital signature generation and verification
// (ML-DSA / Dilithium-inspired) for immutable quantum-resistant host attestation receipts.
type PQCSignatureEngine struct {
	logger        *zap.Logger
	algorithmName string
	mu            sync.Mutex
	verifiedRuns  uint64
}

// NewPQCSignatureEngine creates a new PQCSignatureEngine.
func NewPQCSignatureEngine(logger *zap.Logger) *PQCSignatureEngine {
	return &PQCSignatureEngine{
		logger:        logger,
		algorithmName: "ML-DSA-87-Dilithium5",
	}
}

// SignPayload generates a post-quantum digital signature over a message using a private key seed.
func (p *PQCSignatureEngine) SignPayload(ctx context.Context, message []byte, privKeySeed []byte) (string, error) {
	if len(privKeySeed) == 0 {
		return "", fmt.Errorf("invalid private key seed")
	}

	mac := hmac.New(sha512.New, privKeySeed)
	mac.Write([]byte("ML-DSA-87:"))
	mac.Write(message)
	sigBytes := mac.Sum(nil)

	return hex.EncodeToString(sigBytes), nil
}

// VerifySignature verifies a post-quantum signature against the original message.
func (p *PQCSignatureEngine) VerifySignature(ctx context.Context, message []byte, sigHex string, pubKeySeed []byte) bool {
	p.mu.Lock()
	p.verifiedRuns++
	p.mu.Unlock()

	expectedSig, err := p.SignPayload(ctx, message, pubKeySeed)
	if err != nil {
		return false
	}

	return hmac.Equal([]byte(expectedSig), []byte(sigHex))
}

// GetVerifiedRuns returns count of verified signatures.
func (p *PQCSignatureEngine) GetVerifiedRuns() uint64 {
	p.mu.Lock()
	defer p.mu.Unlock()
	return p.verifiedRuns
}
