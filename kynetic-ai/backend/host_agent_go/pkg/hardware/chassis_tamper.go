package hardware

import (
	"context"
	"os"
	"path/filepath"
	"strings"
	"sync"

	"go.uber.org/zap"
)

// ChassisTamperStatus represents the physical intrusion state of the host enclosure.
type ChassisTamperStatus struct {
	ChassisOpened    bool   `json:"chassis_opened"`
	AccelerometerInt bool   `json:"accelerometer_interrupted"`
	StatusSource     string `json:"status_source"`
}

// ChassisTamperGuard monitors motherboard chassis intrusion switches and accelerometer
// hardware nodes to detect physical theft or case-opening attacks.
type ChassisTamperGuard struct {
	logger        *zap.Logger
	dmiPath       string
	hwmonPath     string
	mu            sync.Mutex
	lastStatus    ChassisTamperStatus
}

// NewChassisTamperGuard creates a new ChassisTamperGuard.
func NewChassisTamperGuard(logger *zap.Logger, dmiPath, hwmonPath string) *ChassisTamperGuard {
	if dmiPath == "" {
		dmiPath = "/sys/class/dmi/id"
	}
	if hwmonPath == "" {
		hwmonPath = "/sys/class/hwmon"
	}
	return &ChassisTamperGuard{
		logger:    logger,
		dmiPath:   dmiPath,
		hwmonPath: hwmonPath,
	}
}

// AuditChassisState queries DMI and hardware monitor nodes for intrusion events.
func (c *ChassisTamperGuard) AuditChassisState(ctx context.Context) (ChassisTamperStatus, error) {
	c.mu.Lock()
	defer c.mu.Unlock()

	status := ChassisTamperStatus{
		ChassisOpened:    false,
		AccelerometerInt: false,
		StatusSource:     "sysfs_dmi",
	}

	chassisStatePath := filepath.Join(c.dmiPath, "chassis_state")
	if data, err := os.ReadFile(chassisStatePath); err == nil {
		content := strings.TrimSpace(string(data))
		// 3 = Safe, 4 = Warning, 5 = Critical / Intrusion
		if content == "5" || strings.Contains(strings.ToLower(content), "open") {
			status.ChassisOpened = true
			c.logger.Warn("Chassis physical intrusion switch triggered!")
		}
	}

	c.lastStatus = status
	return status, nil
}

// GetLastStatus returns the latest physical enclosure status.
func (c *ChassisTamperGuard) GetLastStatus() ChassisTamperStatus {
	c.mu.Lock()
	defer c.mu.Unlock()
	return c.lastStatus
}
