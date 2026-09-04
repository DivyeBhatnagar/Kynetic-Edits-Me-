package hardware

import (
	"fmt"
	"sync"
	"time"
)

// ThermalLimits configures maximum safe temperature and power boundaries
type ThermalLimits struct {
	MaxCoreTempC      float64 `json:"max_core_temp_c"`      // default: 83.0°C
	MaxHotspotTempC   float64 `json:"max_hotspot_temp_c"`   // default: 95.0°C
	MaxSustainedSecs  int     `json:"max_sustained_secs"`   // default: 15 seconds
	PowerCapWatts     int     `json:"power_cap_watts"`      // 0 = default TDP
}

// ThermalGovernor monitors GPU thermals and triggers automatic throttling / shutdown
type ThermalGovernor struct {
	mu                sync.Mutex
	Limits            ThermalLimits
	OverheatStartTime *time.Time
	TripwireTriggered bool
	LastSample        GPUTelemetry
}

// NewThermalGovernor creates a governor with default hardware safety limits
func NewThermalGovernor(limits *ThermalLimits) *ThermalGovernor {
	if limits == nil {
		limits = &ThermalLimits{
			MaxCoreTempC:     83.0,
			MaxHotspotTempC:  95.0,
			MaxSustainedSecs: 15,
			PowerCapWatts:    0,
		}
	}
	return &ThermalGovernor{
		Limits: *limits,
	}
}

// EvaluateSample evaluates an incoming telemetry sample against thermal thresholds
func (g *ThermalGovernor) EvaluateSample(sample GPUTelemetry) (action string, err error) {
	g.mu.Lock()
	defer g.mu.Unlock()

	g.LastSample = sample
	isOverheating := sample.TemperatureC >= g.Limits.MaxCoreTempC

	if isOverheating {
		now := time.Now().UTC()
		if g.OverheatStartTime == nil {
			g.OverheatStartTime = &now
		}

		duration := now.Sub(*g.OverheatStartTime).Seconds()
		if duration >= float64(g.Limits.MaxSustainedSecs) {
			g.TripwireTriggered = true
			return "TRIPWIRE_TERMINATE", fmt.Errorf(
				"thermal emergency: GPU %.1f°C exceeded limit %.1f°C for %.0fs",
				sample.TemperatureC, g.Limits.MaxCoreTempC, duration,
			)
		}
		return "THROTTLE", nil
	}

	// Temperature back in safe zone
	g.OverheatStartTime = nil
	g.TripwireTriggered = false
	return "NORMAL", nil
}

// IsTripwireActive checks if thermal emergency shutdown has been triggered
func (g *ThermalGovernor) IsTripwireActive() bool {
	g.mu.Lock()
	defer g.mu.Unlock()
	return g.TripwireTriggered
}
