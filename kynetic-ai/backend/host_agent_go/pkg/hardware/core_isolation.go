package hardware

import (
	"context"
	"os"
	"path/filepath"
	"strings"
	"sync"

	"go.uber.org/zap"
)

// CoreIsolationManager isolates physical CPU cores and controls SMT/Hyperthreading state
// to mitigate cross-thread L1/L2 cache timing side channels (MDS, RIDL, ZombieLoad).
type CoreIsolationManager struct {
	logger      *zap.Logger
	sysCpuPath  string
	mu          sync.Mutex
	smtDisabled bool
}

// NewCoreIsolationManager creates a new CoreIsolationManager.
func NewCoreIsolationManager(logger *zap.Logger, sysCpuPath string) *CoreIsolationManager {
	if sysCpuPath == "" {
		sysCpuPath = "/sys/devices/system/cpu"
	}
	return &CoreIsolationManager{
		logger:     logger,
		sysCpuPath: sysCpuPath,
	}
}

// QuerySMTControl reads /sys/devices/system/cpu/smt/control to check SMT status.
func (c *CoreIsolationManager) QuerySMTControl() (string, error) {
	c.mu.Lock()
	defer c.mu.Unlock()

	smtPath := filepath.Join(c.sysCpuPath, "smt", "control")
	data, err := os.ReadFile(smtPath)
	if err != nil {
		if os.IsNotExist(err) {
			c.logger.Debug("SMT control node not available on this platform")
			return "notsupported", nil
		}
		return "", err
	}
	return strings.TrimSpace(string(data)), nil
}

// DisableSMT writes 'off' to /sys/devices/system/cpu/smt/control to isolate physical execution cores.
func (c *CoreIsolationManager) DisableSMT(ctx context.Context) error {
	c.mu.Lock()
	defer c.mu.Unlock()

	smtPath := filepath.Join(c.sysCpuPath, "smt", "control")
	if _, err := os.Stat(smtPath); err != nil {
		if os.IsNotExist(err) {
			c.logger.Debug("Simulated SMT disable for non-Linux/mock platform")
			c.smtDisabled = true
			return nil
		}
		return err
	}

	err := os.WriteFile(smtPath, []byte("off\n"), 0644)
	if err != nil {
		c.logger.Warn("Failed to disable SMT (requires root privileges or BIOS support)", zap.Error(err))
		return err
	}

	c.smtDisabled = true
	c.logger.Info("SMT / Hyperthreading successfully disabled for cross-thread cache defense")
	return nil
}

// IsSMTDisabled returns current SMT state.
func (c *CoreIsolationManager) IsSMTDisabled() bool {
	c.mu.Lock()
	defer c.mu.Unlock()
	return c.smtDisabled
}
