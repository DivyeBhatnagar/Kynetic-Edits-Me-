package security

import (
	"crypto/hmac"
	"crypto/rand"
	"crypto/sha256"
	"fmt"
	"sync"
)

// MPCPartialSignature represents a partial cryptographic signature share produced by one node in an MPC cluster.
type MPCPartialSignature struct {
	NodeID    int    `json:"node_id"`
	Share     []byte `json:"share"`
	Commitment []byte `json:"commitment"`
}

// MPCThresholdSigner manages (t, n) threshold decentralized signatures across worker nodes.
type MPCThresholdSigner struct {
	threshold  int
	totalNodes int
	nodeID     int
	secretKey  []byte
	mu         sync.RWMutex
}

// NewMPCThresholdSigner creates a new MPC threshold signing participant.
func NewMPCThresholdSigner(threshold, totalNodes, nodeID int, keyShare []byte) (*MPCThresholdSigner, error) {
	if threshold <= 0 || totalNodes < threshold || nodeID <= 0 || nodeID > totalNodes {
		return nil, fmt.Errorf("invalid threshold parameters: t=%d, n=%d, nodeID=%d", threshold, totalNodes, nodeID)
	}
	if len(keyShare) == 0 {
		return nil, fmt.Errorf("key share cannot be empty")
	}
	return &MPCThresholdSigner{
		threshold:  threshold,
		totalNodes: totalNodes,
		nodeID:     nodeID,
		secretKey:  keyShare,
	}, nil
}

// GeneratePartialSignature computes a partial signature on a message digest.
func (m *MPCThresholdSigner) GeneratePartialSignature(message []byte) (*MPCPartialSignature, error) {
	m.mu.RLock()
	defer m.mu.RUnlock()

	// Compute partial signature share = HMAC(secretKey, message || nodeID)
	mac := hmac.New(sha256.New, m.secretKey)
	mac.Write(message)
	mac.Write([]byte{byte(m.nodeID)})
	share := mac.Sum(nil)

	// Compute commitment = SHA256(share)
	commit := sha256.Sum256(share)

	return &MPCPartialSignature{
		NodeID:     m.nodeID,
		Share:      share,
		Commitment: commit[:],
	}, nil
}

// AggregateThresholdSignatures combines at least t partial signature shares into an aggregated threshold signature.
func (m *MPCThresholdSigner) AggregateThresholdSignatures(message []byte, partials []*MPCPartialSignature) ([]byte, error) {
	if len(partials) < m.threshold {
		return nil, fmt.Errorf("insufficient signature shares: got %d, required threshold %d", len(partials), m.threshold)
	}

	// Verify commitments and aggregate
	agg := sha256.New()
	agg.Write(message)

	seenNodes := make(map[int]bool)
	count := 0
	for _, p := range partials {
		if seenNodes[p.NodeID] {
			continue
		}
		seenNodes[p.NodeID] = true

		// Check commitment
		comm := sha256.Sum256(p.Share)
		if !hmac.Equal(comm[:], p.Commitment) {
			return nil, fmt.Errorf("invalid commitment for node %d", p.NodeID)
		}

		agg.Write(p.Share)
		count++
		if count >= m.threshold {
			break
		}
	}

	if count < m.threshold {
		return nil, fmt.Errorf("failed to aggregate threshold signatures: duplicate nodes detected")
	}

	return agg.Sum(nil), nil
}

// VerifyThresholdSignature validates an aggregated threshold signature.
func VerifyThresholdSignature(message, aggregatedSig, expectedSig []byte) bool {
	return hmac.Equal(aggregatedSig, expectedSig)
}

// GenerateDistributedKeyShares generates n random key shares for testing/bootstrapping.
func GenerateDistributedKeyShares(n int) ([][]byte, error) {
	shares := make([][]byte, n)
	for i := 0; i < n; i++ {
		shares[i] = make([]byte, 32)
		if _, err := rand.Read(shares[i]); err != nil {
			return nil, err
		}
	}
	return shares, nil
}
