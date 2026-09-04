package hardware

import (
	"context"
	"math/rand"
	"sync"

	"go.uber.org/zap"
)

// ThermalDitherManager injects micro-variations into cooling fan duty cycles (PWM)
// to eliminate acoustic side-channel fingerprinting of neural network compute passes.
type ThermalDitherManager struct {
	logger        *zap.Logger
	ditherRangePct float64
	mu            sync.Mutex
	ditherEvents  uint64
}

// NewThermalDitherManager creates a new ThermalDitherManager.
func NewThermalDitherManager(logger *zap.Logger, ditherRangePct float64) *ThermalDitherManager {
	if ditherRangePct <= 0 {
		ditherRangePct = 3.0 // 3% random PWM dithering
	}
	return &ThermalDitherManager{
		logger:         logger,
		ditherRangePct: ditherRangePct,
	}
}

// DitherFanSpeed applies a randomized dithering offset to the calculated fan speed percentage.
func (t *ThermalDitherManager) DitherFanSpeed(ctx context.Context, baseFanPct float64) float64 {
	t.mu.Lock()
	t.ditherEvents++
	t.mu.Unlock()

	// Random jitter between [-ditherRangePct, +ditherRangePct]
	jitter := (rand.Float64()*2 - 1.0) * t.ditherRangePct
	fuzzedPct := baseFanPct + jitter

	if fuzzedPct < 0 {
		fuzzedPct = 0
	} else if fuzzedPct > 100 {
		fuzzedPct = 100
	}

	return fuzzedPct
}

// GetDitherEventsCount returns total dithering transformations executed.
func (t *ThermalDitherManager) GetDitherEventsCount() uint64 {
	t.mu.Lock()
	defer t.mu.Unlock()
	return t.ditherEvents
}
