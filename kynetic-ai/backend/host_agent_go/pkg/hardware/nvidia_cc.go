package hardware

import (
	"context"
	"os"
	"path/filepath"
	"strings"
	"sync"

	"go.uber.org/zap"
)

// CCMode represents the NVIDIA Confidential Computing operating status.
type CCMode string

const (
	CCModeDisabled CCMode = "disabled"
	CCModeDevTools CCMode = "devtools"
	CCModeOn       CCMode = "on"
)

// NvidiaCCManager checks and manages NVIDIA Hopper/Blackwell Confidential Computing
// (APEX) state and PCIe link encryption (SPDM).
type NvidiaCCManager struct {
	logger     *zap.Logger
	sysfsPath  string
	mu         sync.Mutex
	activeMode CCMode
}

// NewNvidiaCCManager creates a new NvidiaCCManager.
func NewNvidiaCCManager(logger *zap.Logger, sysfsPath string) *NvidiaCCManager {
	if sysfsPath == "" {
		sysfsPath = "/sys/bus/pci/drivers/nvidia"
	}
	return &NvidiaCCManager{
		logger:     logger,
		sysfsPath:  sysfsPath,
		activeMode: CCModeDisabled,
	}
}

// QueryCCMode inspects NVIDIA driver sysfs or NVML endpoints to verify hardware enclave status.
func (n *NvidiaCCManager) QueryCCMode(ctx context.Context) (CCMode, error) {
	n.mu.Lock()
	defer n.mu.Unlock()

	ccPath := filepath.Join(n.sysfsPath, "cc_mode")
	data, err := os.ReadFile(ccPath)
	if err != nil {
		if os.IsNotExist(err) {
			n.logger.Debug("NVIDIA CC sysfs node not present (simulated mode for non-Hopper GPU)")
			n.activeMode = CCModeDisabled
			return CCModeDisabled, nil
		}
		return CCModeDisabled, err
	}

	content := strings.TrimSpace(string(data))
	switch strings.ToLower(content) {
	case "on", "1", "enabled":
		n.activeMode = CCModeOn
	case "devtools", "debug":
		n.activeMode = CCModeDevTools
	default:
		n.activeMode = CCModeDisabled
	}

	n.logger.Info("NVIDIA Confidential Computing mode queried", zap.String("mode", string(n.activeMode)))
	return n.activeMode, nil
}

// IsConfidentialComputeActive returns true if hardware enclave is active.
func (n *NvidiaCCManager) IsConfidentialComputeActive() bool {
	n.mu.Lock()
	defer n.mu.Unlock()
	return n.activeMode == CCModeOn
}
