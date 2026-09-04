package hardware

import (
	"fmt"
	"math"
	"sync"
)

// PowerSlewSample represents a high-frequency voltage and current reading from the GPU VRM / PCIe bus.
type PowerSlewSample struct {
	TimestampMicrosec int64   `json:"timestamp_us"`
	VoltageVolts      float64 `json:"voltage_v"`
	CurrentAmps       float64 `json:"current_a"`
}

// PowerSlewTrapConfig holds thresholds for detecting electromagnetic and voltage fault injections.
type PowerSlewTrapConfig struct {
	MaxVoltageDroopRateVoltsPerMicrosec float64 `json:"max_dv_dt"` // e.g. > 0.05 V/us droop
	MaxCurrentSlewAmpsPerMicrosec       float64 `json:"max_di_dt"` // e.g. > 15.0 A/us spike
	GlitchWindowMicrosec                int64   `json:"glitch_window_us"`
}

// DefaultPowerSlewConfig returns hardened production thresholds.
func DefaultPowerSlewConfig() PowerSlewTrapConfig {
	return PowerSlewTrapConfig{
		MaxVoltageDroopRateVoltsPerMicrosec: 0.05,
		MaxCurrentSlewAmpsPerMicrosec:       15.0,
		GlitchWindowMicrosec:                100,
	}
}

// PowerSlewTrap monitors GPU PCIe and core VRM telemetry to tripwire EMFI (Electromagnetic Fault Injection) attacks.
type PowerSlewTrap struct {
	mu              sync.Mutex
	config          PowerSlewTrapConfig
	lastSample      *PowerSlewSample
	tripwireTripped bool
	glitchAlerts    []string
}

// NewPowerSlewTrap instantiates a new power slew trap.
func NewPowerSlewTrap(cfg PowerSlewTrapConfig) *PowerSlewTrap {
	return &PowerSlewTrap{
		config:       cfg,
		glitchAlerts: make([]string, 0),
	}
}

// IngestTelemetry evaluates a new high-frequency VRM telemetry sample.
func (p *PowerSlewTrap) IngestTelemetry(sample PowerSlewSample) (bool, string) {
	p.mu.Lock()
	defer p.mu.Unlock()

	if p.lastSample == nil {
		p.lastSample = &sample
		return false, "FIRST_SAMPLE_CALIBRATED"
	}

	dt := float64(sample.TimestampMicrosec - p.lastSample.TimestampMicrosec)
	if dt <= 0 {
		dt = 1.0 // Prevent divide-by-zero on concurrent ticks
	}

	dv := math.Abs(sample.VoltageVolts - p.lastSample.VoltageVolts)
	di := math.Abs(sample.CurrentAmps - p.lastSample.CurrentAmps)

	dvDt := dv / dt
	diDt := di / dt

	p.lastSample = &sample

	if dvDt > p.config.MaxVoltageDroopRateVoltsPerMicrosec {
		p.tripwireTripped = true
		alert := fmt.Sprintf("CRITICAL_VOLTAGE_GLITCH_EMFI_DETECTED: dV/dt=%.4f V/us > threshold=%.4f", dvDt, p.config.MaxVoltageDroopRateVoltsPerMicrosec)
		p.glitchAlerts = append(p.glitchAlerts, alert)
		return true, alert
	}

	if diDt > p.config.MaxCurrentSlewAmpsPerMicrosec {
		p.tripwireTripped = true
		alert := fmt.Sprintf("CRITICAL_CURRENT_SPIKE_GLITCH_DETECTED: dI/dt=%.4f A/us > threshold=%.4f", diDt, p.config.MaxCurrentSlewAmpsPerMicrosec)
		p.glitchAlerts = append(p.glitchAlerts, alert)
		return true, alert
	}

	return false, "POWER_SLEW_STABLE"
}

// IsTripped returns true if an EMFI or voltage glitch was detected.
func (p *PowerSlewTrap) IsTripped() bool {
	p.mu.Lock()
	defer p.mu.Unlock()
	return p.tripwireTripped
}
