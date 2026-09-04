package security

import (
	"math"
	"sync"
)

// FGSMPurifier detects high-frequency gradient noise and purifies adversarial input tensors.
type FGSMPurifier struct {
	spatialRadius int
	bitDepthBits  int
	mu            sync.RWMutex
}

// NewFGSMPurifier creates a new adversarial input purifier.
func NewFGSMPurifier(spatialRadius, bitDepthBits int) *FGSMPurifier {
	if spatialRadius <= 0 {
		spatialRadius = 1
	}
	if bitDepthBits <= 0 || bitDepthBits > 8 {
		bitDepthBits = 5 // Reduce 8-bit to 5-bit color space to strip imperceptible perturbations
	}
	return &FGSMPurifier{
		spatialRadius: spatialRadius,
		bitDepthBits:  bitDepthBits,
	}
}

// DetectAdversarialNoise estimates high-frequency perturbation energy in the tensor.
func (p *FGSMPurifier) DetectAdversarialNoise(tensor []float64) (bool, float64) {
	p.mu.RLock()
	defer p.mu.RUnlock()

	if len(tensor) < 2 {
		return false, 0
	}

	// Calculate total variation / second-order gradient differences
	var totalVariation float64
	for i := 1; i < len(tensor); i++ {
		diff := math.Abs(tensor[i] - tensor[i-1])
		totalVariation += diff
	}

	avgVariation := totalVariation / float64(len(tensor)-1)
	isAdversarial := avgVariation > 0.45 // High-frequency jitter threshold

	return isAdversarial, avgVariation
}

// PurifyInputTensor applies median filtering and bit-depth quantization to strip FGSM / PGD perturbations.
func (p *FGSMPurifier) PurifyInputTensor(tensor []float64) []float64 {
	p.mu.RLock()
	defer p.mu.RUnlock()

	purified := make([]float64, len(tensor))
	n := len(tensor)

	// Step 1: Spatial 1D Moving-Average Smoothing
	for i := 0; i < n; i++ {
		start := i - p.spatialRadius
		if start < 0 {
			start = 0
		}
		end := i + p.spatialRadius
		if end >= n {
			end = n - 1
		}

		var sum float64
		count := 0
		for j := start; j <= end; j++ {
			sum += tensor[j]
			count++
		}
		purified[i] = sum / float64(count)
	}

	// Step 2: Bit-Depth Quantization
	levels := math.Pow(2, float64(p.bitDepthBits))
	for i := range purified {
		clamped := math.Max(0.0, math.Min(1.0, purified[i]))
		quantized := math.Round(clamped*(levels-1)) / (levels - 1)
		purified[i] = quantized
	}

	return purified
}
