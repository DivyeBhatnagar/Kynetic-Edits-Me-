package hardware

import (
	"context"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"sync"

	"go.uber.org/zap"
)

// VoltageStatus captures real-time CPU/GPU core voltage readings to detect undervolting attacks.
type VoltageStatus struct {
	CurrentVoltageMv uint32  `json:"current_voltage_mv"`
	NominalVoltageMv uint32  `json:"nominal_voltage_mv"`
	DipPercentage    float64 `json:"dip_percentage"`
	FaultDetected    bool    `json:"fault_detected"`
}

// VoltageFaultDetector monitors CPU VID and GPU voltage regulators to detect fault-injection
// attacks (Plundervolt / VoltPill / CLKSCREW) designed to induce bitflips in AES/RSA operations.
type VoltageFaultDetector struct {
	logger           *zap.Logger
	hwmonPath        string
	nominalMv        uint32
	maxAllowedDipPct float64
	mu               sync.Mutex
	faultCount       uint64
}

// NewVoltageFaultDetector creates a new VoltageFaultDetector.
func NewVoltageFaultDetector(logger *zap.Logger, hwmonPath string, nominalMv uint32) *VoltageFaultDetector {
	if hwmonPath == "" {
		hwmonPath = "/sys/class/hwmon"
	}
	if nominalMv == 0 {
		nominalMv = 1100 // 1.1V standard nominal core voltage
	}
	return &VoltageFaultDetector{
		logger:           logger,
		hwmonPath:        hwmonPath,
		nominalMv:        nominalMv,
		maxAllowedDipPct: 15.0, // Alert if voltage drops >15% below nominal unexpectedly
	}
}

// AuditVoltageRegulators scans `/sys/class/hwmon/hwmon*/in0_input` for abnormal voltage dips.
func (v *VoltageFaultDetector) AuditVoltageRegulators(ctx context.Context) (VoltageStatus, error) {
	v.mu.Lock()
	defer v.mu.Unlock()

	status := VoltageStatus{
		NominalVoltageMv: v.nominalMv,
		CurrentVoltageMv: v.nominalMv,
		DipPercentage:    0.0,
		FaultDetected:    false,
	}

	entries, err := os.ReadDir(v.hwmonPath)
	if err != nil {
		if os.IsNotExist(err) {
			v.logger.Debug("Hwmon path not present (simulated mode for non-Linux/mock platform)")
			return status, nil
		}
		return status, err
	}

	for _, entry := range entries {
		vInFile := filepath.Join(v.hwmonPath, entry.Name(), "in0_input")
		if data, err := os.ReadFile(vInFile); err == nil {
			val, err := strconv.ParseUint(strings.TrimSpace(string(data)), 10, 32)
			if err == nil && val > 0 {
				status.CurrentVoltageMv = uint32(val)
				if status.CurrentVoltageMv < v.nominalMv {
					dip := float64(v.nominalMv-status.CurrentVoltageMv) / float64(v.nominalMv) * 100.0
					status.DipPercentage = dip
					if dip > v.maxAllowedDipPct {
						status.FaultDetected = true
						v.faultCount++
						v.logger.Warn("VoltageFaultDetector: Suspicious silicon undervolting dip detected (Plundervolt / VoltPill threat)!",
							zap.Uint32("voltage_mv", status.CurrentVoltageMv),
							zap.Float64("dip_pct", dip),
						)
					}
				}
				break
			}
		}
	}

	return status, nil
}

// GetFaultCount returns count of identified fault-injection anomalies.
func (v *VoltageFaultDetector) GetFaultCount() uint64 {
	v.mu.Lock()
	defer v.mu.Unlock()
	return v.faultCount
}
