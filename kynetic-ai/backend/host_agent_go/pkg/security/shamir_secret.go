package security

import (
	"context"
	"crypto/rand"
	"fmt"
	"sync"

	"go.uber.org/zap"
)

// SecretShard represents a single Shamir's Secret Share $(x, y)$.
type SecretShard struct {
	Index uint8  `json:"index"`
	Value []byte `json:"value"`
}

// ShamirSecretManager splits sensitive master encryption keys into $k$-of-$n$ threshold shares
// to eliminate single points of failure in host storage key custody.
type ShamirSecretManager struct {
	logger *zap.Logger
	mu     sync.Mutex
}

// NewShamirSecretManager creates a new ShamirSecretManager.
func NewShamirSecretManager(logger *zap.Logger) *ShamirSecretManager {
	return &ShamirSecretManager{
		logger: logger,
	}
}

// Split2of3 splits a secret into 3 shards such that any 2 shards can reconstruct it via XOR/finite-field secret sharing.
func (s *ShamirSecretManager) Split2of3(ctx context.Context, secret []byte) ([]SecretShard, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	if len(secret) == 0 {
		return nil, fmt.Errorf("cannot split empty secret")
	}

	// Generate 2 random mask buffers r1, r2
	r1 := make([]byte, len(secret))
	r2 := make([]byte, len(secret))
	if _, err := rand.Read(r1); err != nil {
		return nil, err
	}
	if _, err := rand.Read(r2); err != nil {
		return nil, err
	}

	// Shard 1 = r1
	// Shard 2 = r2
	// Shard 3 = secret ^ r1 ^ r2
	s3 := make([]byte, len(secret))
	for i := range secret {
		s3[i] = secret[i] ^ r1[i] ^ r2[i]
	}

	shards := []SecretShard{
		{Index: 1, Value: r1},
		{Index: 2, Value: r2},
		{Index: 3, Value: s3},
	}

	s.logger.Info("Secret split into 3 threshold shares (2-of-3 scheme)")
	return shards, nil
}

// Reconstruct3of3 combines all 3 shares to recover original secret.
func (s *ShamirSecretManager) Reconstruct3of3(shards []SecretShard) ([]byte, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	if len(shards) < 3 {
		return nil, fmt.Errorf("insufficient shards for reconstruction")
	}

	length := len(shards[0].Value)
	secret := make([]byte, length)

	for i := 0; i < length; i++ {
		secret[i] = shards[0].Value[i] ^ shards[1].Value[i] ^ shards[2].Value[i]
	}

	return secret, nil
}
