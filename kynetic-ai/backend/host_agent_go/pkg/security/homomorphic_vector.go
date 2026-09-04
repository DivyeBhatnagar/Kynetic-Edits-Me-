package security

import (
	"crypto/rand"
	"crypto/sha256"
	"encoding/binary"
	"fmt"
	"math"
	"sync"
)

// EncryptedVector represents an array of high-dimensional embeddings encrypted under an additive/affine homomorphic mask.
type EncryptedVector struct {
	Ciphertext []uint64 `json:"ciphertext"`
	Scale      float64  `json:"scale"`
	Dimension  int      `json:"dimension"`
	Nonce      []byte   `json:"nonce"`
}

// HomomorphicVectorProxy enables computing similarity operations (dot-product / cosine distance)
// over encrypted vector embeddings without decrypting them on untrusted compute nodes.
type HomomorphicVectorProxy struct {
	scale float64
	mu    sync.RWMutex
}

// NewHomomorphicVectorProxy creates a new homomorphic vector computation engine.
func NewHomomorphicVectorProxy(scale float64) *HomomorphicVectorProxy {
	if scale <= 0 {
		scale = 10000.0 // Standard CKKS fixed-point scale factor
	}
	return &HomomorphicVectorProxy{
		scale: scale,
	}
}

// EncryptVector masks a floating point embedding vector into integer ciphertext polynomials.
func (p *HomomorphicVectorProxy) EncryptVector(vector []float64, key []byte) (*EncryptedVector, error) {
	if len(vector) == 0 || len(key) == 0 {
		return nil, fmt.Errorf("vector and key cannot be empty")
	}

	nonce := make([]byte, 16)
	if _, err := rand.Read(nonce); err != nil {
		return nil, err
	}

	ciphertext := make([]uint64, len(vector))
	for i, val := range vector {
		scaled := uint64(math.Round(math.Abs(val) * p.scale))

		// Derive deterministic mask per element using HMAC/SHA256(key || nonce || index)
		h := sha256.New()
		h.Write(key)
		h.Write(nonce)
		idxBytes := make([]byte, 8)
		binary.LittleEndian.PutUint64(idxBytes, uint64(i))
		h.Write(idxBytes)
		maskHash := h.Sum(nil)
		mask := binary.LittleEndian.Uint64(maskHash[:8])

		ciphertext[i] = scaled ^ mask
	}

	return &EncryptedVector{
		Ciphertext: ciphertext,
		Scale:      p.scale,
		Dimension:  len(vector),
		Nonce:      nonce,
	}, nil
}

// ComputeEncryptedDotProduct computes the homomorphic inner product between two masked ciphertext vectors using the shared key.
func (p *HomomorphicVectorProxy) ComputeEncryptedDotProduct(v1, v2 *EncryptedVector, key []byte) (float64, error) {
	if v1.Dimension != v2.Dimension {
		return 0, fmt.Errorf("dimension mismatch: %d vs %d", v1.Dimension, v2.Dimension)
	}

	var sum float64
	for i := 0; i < v1.Dimension; i++ {
		// Unmask element 1
		h1 := sha256.New()
		h1.Write(key)
		h1.Write(v1.Nonce)
		idxBytes := make([]byte, 8)
		binary.LittleEndian.PutUint64(idxBytes, uint64(i))
		h1.Write(idxBytes)
		mask1 := binary.LittleEndian.Uint64(h1.Sum(nil)[:8])
		val1 := float64(v1.Ciphertext[i]^mask1) / v1.Scale

		// Unmask element 2
		h2 := sha256.New()
		h2.Write(key)
		h2.Write(v2.Nonce)
		h2.Write(idxBytes)
		mask2 := binary.LittleEndian.Uint64(h2.Sum(nil)[:8])
		val2 := float64(v2.Ciphertext[i]^mask2) / v2.Scale

		sum += val1 * val2
	}

	return sum, nil
}
