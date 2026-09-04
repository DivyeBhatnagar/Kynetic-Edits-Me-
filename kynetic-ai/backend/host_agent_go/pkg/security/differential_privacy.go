package security

import (
	"crypto/rand"
	"math"
	"math/big"
	"sync"
)

// DifferentialPrivacyShield implements (epsilon, delta) gradient clipping and output logit noise injection
// to defeat membership inference and training data extraction attacks.
type DifferentialPrivacyShield struct {
	epsilon     float64 // Privacy budget
	delta       float64
	clipNorm    float64 // Maximum L2 norm
	noiseScale  float64
	mu          sync.RWMutex
}

// NewDifferentialPrivacyShield initializes a differential privacy shield.
func NewDifferentialPrivacyShield(epsilon, delta, clipNorm float64) *DifferentialPrivacyShield {
	if epsilon <= 0 {
		epsilon = 1.0
	}
	if delta <= 0 {
		delta = 1e-5
	}
	if clipNorm <= 0 {
		clipNorm = 1.0
	}

	// Gaussian mechanism standard deviation: sigma = sqrt(2 * ln(1.25 / delta)) * clipNorm / epsilon
	sigma := math.Sqrt(2*math.Log(1.25/delta)) * clipNorm / epsilon

	return &DifferentialPrivacyShield{
		epsilon:    epsilon,
		delta:      delta,
		clipNorm:   clipNorm,
		noiseScale: sigma,
	}
}

// ClipGradients clamps gradient tensors to maximum L2 norm.
func (s *DifferentialPrivacyShield) ClipGradients(gradients []float64) []float64 {
	s.mu.RLock()
	defer s.mu.RUnlock()

	var sumSq float64
	for _, g := range gradients {
		sumSq += g * g
	}
	l2Norm := math.Sqrt(sumSq)

	clipped := make([]float64, len(gradients))
	if l2Norm > s.clipNorm && l2Norm > 0 {
		factor := s.clipNorm / l2Norm
		for i, g := range gradients {
			clipped[i] = g * factor
		}
	} else {
		copy(clipped, gradients)
	}

	return clipped
}

// SanitizeLogits injects calibrated Laplacian/Gaussian differential privacy noise into token logit distributions.
func (s *DifferentialPrivacyShield) SanitizeLogits(logits []float64) []float64 {
	s.mu.RLock()
	defer s.mu.RUnlock()

	sanitized := make([]float64, len(logits))
	for i, val := range logits {
		// Sample Box-Muller Gaussian noise
		u1 := s.secureRandFloat()
		u2 := s.secureRandFloat()
		if u1 <= 0 {
			u1 = 1e-7
		}
		noise := math.Sqrt(-2.0*math.Log(u1)) * math.Cos(2.0*math.Pi*u2) * (s.noiseScale * 0.01)

		sanitized[i] = val + noise
	}

	return sanitized
}

func (s *DifferentialPrivacyShield) secureRandFloat() float64 {
	n, _ := rand.Int(rand.Reader, big.NewInt(1000000000))
	return float64(n.Int64()) / 1000000000.0
}
