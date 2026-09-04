package hardware

import (
	"context"
	"math"
	"math/rand"
	"sync"
	"time"

	"go.uber.org/zap"
)

// MaskedTelemetry wraps actual telemetry with calibrated jitter to thwart
// acoustic and power consumption side-channel analysis by hostile AI workloads.
type MaskedTelemetry struct {
	ReportedTempC    float64   `json:"reported_temp_c"`
	ReportedFanSpeed uint32    `json:"reported_fan_speed_rpm"`
	ReportedWatts    float64   `json:"reported_watts"`
	IsFuzzed         bool      `json:"is_fuzzed"`
	Timestamp        time.Time `json:"timestamp"`
}

// TelemetryMasker injects differential noise / jitter into host fan RPM, thermal,
// and power queries exposed to guest workloads or sandbox queries.
type TelemetryMasker struct {
	logger        *zap.Logger
	noiseLevel    float64 // e.g. 0.05 for 5% jitter
	mu            sync.Mutex
	lastTelemetry MaskedTelemetry
}

// NewTelemetryMasker creates a new TelemetryMasker.
func NewTelemetryMasker(logger *zap.Logger, noiseLevel float64) *TelemetryMasker {
	if noiseLevel <= 0 {
		noiseLevel = 0.04 // 4% default differential privacy noise
	}
	return &TelemetryMasker{
		logger:     logger,
		noiseLevel: noiseLevel,
	}
}

// FuzzTelemetry applies random uniform jitter within [-noiseLevel, +noiseLevel] to raw telemetry.
func (t *TelemetryMasker) FuzzTelemetry(ctx context.Context, rawTempC float64, rawFanRPM uint32, rawWatts float64) MaskedTelemetry {
	t.mu.Lock()
	defer t.mu.Unlock()

	genJitter := func() float64 {
		// Random float in range [-noiseLevel, +noiseLevel]
		return (rand.Float64()*2 - 1.0) * t.noiseLevel
	}

	tempJitter := genJitter()
	fanJitter := genJitter()
	wattsJitter := genJitter()

	fuzzedTemp := math.Round((rawTempC*(1.0+tempJitter))*10) / 10
	fuzzedFan := uint32(float64(rawFanRPM) * (1.0 + fanJitter))
	fuzzedWatts := math.Round((rawWatts*(1.0+wattsJitter))*10) / 10

	t.lastTelemetry = MaskedTelemetry{
		ReportedTempC:    fuzzedTemp,
		ReportedFanSpeed: fuzzedFan,
		ReportedWatts:    fuzzedWatts,
		IsFuzzed:         true,
		Timestamp:        time.Now(),
	}

	return t.lastTelemetry
}

// GetLastTelemetry returns the most recently fuzzed telemetry report.
func (t *TelemetryMasker) GetLastTelemetry() MaskedTelemetry {
	t.mu.Lock()
	defer t.mu.Unlock()
	return t.lastTelemetry
}
