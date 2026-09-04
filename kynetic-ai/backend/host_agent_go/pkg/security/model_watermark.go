package security

import (
	"crypto/hmac"
	"crypto/sha256"
	"fmt"
	"math"
	"sync"
)

// ModelWatermarkVerifier injects and verifies mathematical trigger watermarks into AI model weights and layer activations.
type ModelWatermarkVerifier struct {
	secretKey []byte
	threshold float64
	mu        sync.RWMutex
}

// NewModelWatermarkVerifier creates a new model watermark engine.
func NewModelWatermarkVerifier(secretKey []byte, correlationThreshold float64) (*ModelWatermarkVerifier, error) {
	if len(secretKey) == 0 {
		return nil, fmt.Errorf("secret key cannot be empty")
	}
	if correlationThreshold <= 0 || correlationThreshold > 1.0 {
		correlationThreshold = 0.85
	}
	return &ModelWatermarkVerifier{
		secretKey: secretKey,
		threshold: correlationThreshold,
	}, nil
}

// GenerateTriggerVector produces a deterministic, high-dimensional pseudo-random trigger pattern from the secret key.
func (v *ModelWatermarkVerifier) GenerateTriggerVector(dim int) []float64 {
	v.mu.RLock()
	defer v.mu.RUnlock()

	pattern := make([]float64, dim)
	for i := 0; i < dim; i++ {
		h := hmac.New(sha256.New, v.secretKey)
		h.Write([]byte(fmt.Sprintf("watermark_dim_%d", i)))
		hash := h.Sum(nil)

		// Convert first 4 bytes to float in [-1.0, 1.0]
		val := float64(int32(hash[0])<<24|int32(hash[1])<<16|int32(hash[2])<<8|int32(hash[3])) / float64(math.MaxInt32)
		pattern[i] = val
	}
	return pattern
}

// EmbedWatermark applies an imperceptible additive mathematical watermark into weight tensors.
func (v *ModelWatermarkVerifier) EmbedWatermark(weights []float64, alpha float64) []float64 {
	if alpha <= 0 {
		alpha = 0.001 // Imperceptible scaling factor
	}
	trigger := v.GenerateTriggerVector(len(weights))
	watermarked := make([]float64, len(weights))

	for i := range weights {
		watermarked[i] = weights[i] + alpha*trigger[i]
	}
	return watermarked
}

// VerifyWatermark calculates the Pearson correlation coefficient between suspected weights/activations and the secret trigger.
func (v *ModelWatermarkVerifier) VerifyWatermark(suspectWeights []float64) (bool, float64) {
	trigger := v.GenerateTriggerVector(len(suspectWeights))

	var meanSuspect, meanTrigger float64
	n := float64(len(suspectWeights))
	if n == 0 {
		return false, 0
	}

	for i := range suspectWeights {
		meanSuspect += suspectWeights[i]
		meanTrigger += trigger[i]
	}
	meanSuspect /= n
	meanTrigger /= n

	var numerator, denSuspect, denTrigger float64
	for i := range suspectWeights {
		diffS := suspectWeights[i] - meanSuspect
		diffT := trigger[i] - meanTrigger
		numerator += diffS * diffT
		denSuspect += diffS * diffS
		denTrigger += diffT * diffT
	}

	if denSuspect == 0 || denTrigger == 0 {
		return false, 0
	}

	correlation := math.Abs(numerator / math.Sqrt(denSuspect*denTrigger))
	isVerified := correlation >= v.threshold

	return isVerified, correlation
}
