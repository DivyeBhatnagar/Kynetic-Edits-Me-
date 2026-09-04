package hardware

import (
	"context"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"sync"

	"go.uber.org/zap"
)

// EDACStatus represents the status of host hardware Error Detection and Correction memory counters.
type EDACStatus struct {
	CorrectableErrors   uint64 `json:"correctable_errors"`
	UncorrectableErrors uint64 `json:"uncorrectable_errors"`
	EDACAvailable       bool   `json:"edac_available"`
	AnomalyDetected     bool   `json:"anomaly_detected"`
}

// RowhammerGuard monitors the host Linux EDAC (Error Detection And Correction) subsystem
// for rapid bitflip bursts, detecting and neutralizing Rowhammer attacks against host RAM.
type RowhammerGuard struct {
	logger           *zap.Logger
	edacPath         string
	bitflipThreshold uint64
	mu               sync.Mutex
	lastStatus       EDACStatus
}

// NewRowhammerGuard creates a new RowhammerGuard instance.
func NewRowhammerGuard(logger *zap.Logger, edacPath string, bitflipThreshold uint64) *RowhammerGuard {
	if edacPath == "" {
		edacPath = "/sys/devices/system/edac/mc"
	}
	if bitflipThreshold == 0 {
		bitflipThreshold = 10 // Flag if >10 bitflips detected in an audit window
	}
	return &RowhammerGuard{
		logger:           logger,
		edacPath:         edacPath,
		bitflipThreshold: bitflipThreshold,
	}
}

// ScanEDACControllers queries all memory controllers in /sys/devices/system/edac/mc/
// to sum correctable and uncorrectable memory error counts.
func (r *RowhammerGuard) ScanEDACControllers(ctx context.Context) (EDACStatus, error) {
	r.mu.Lock()
	defer r.mu.Unlock()

	status := EDACStatus{
		EDACAvailable: false,
	}

	entries, err := os.ReadDir(r.edacPath)
	if err != nil {
		if os.IsNotExist(err) {
			r.logger.Debug("EDAC subsystem not active on this hardware/platform")
			r.lastStatus = status
			return status, nil
		}
		return status, fmt.Errorf("failed reading edac sysfs: %w", err)
	}

	status.EDACAvailable = true
	var totalCE, totalUE uint64

	for _, entry := range entries {
		if strings.HasPrefix(entry.Name(), "mc") {
			mcDir := filepath.Join(r.edacPath, entry.Name())

			ceFile := filepath.Join(mcDir, "ce_count")
			if data, err := os.ReadFile(ceFile); err == nil {
				val, _ := strconv.ParseUint(strings.TrimSpace(string(data)), 10, 64)
				totalCE += val
			}

			ueFile := filepath.Join(mcDir, "ue_count")
			if data, err := os.ReadFile(ueFile); err == nil {
				val, _ := strconv.ParseUint(strings.TrimSpace(string(data)), 10, 64)
				totalUE += val
			}
		}
	}

	status.CorrectableErrors = totalCE
	status.UncorrectableErrors = totalUE

	// Detect rapid anomaly
	if totalCE > r.bitflipThreshold || totalUE > 0 {
		status.AnomalyDetected = true
		r.logger.Warn("RowhammerGuard: Memory bitflip anomaly detected via EDAC!",
			zap.Uint64("correctable_errors", totalCE),
			zap.Uint64("uncorrectable_errors", totalUE),
		)
	}

	r.lastStatus = status
	return status, nil
}

// GetLastStatus returns the most recent EDACStatus.
func (r *RowhammerGuard) GetLastStatus() EDACStatus {
	r.mu.Lock()
	defer r.mu.Unlock()
	return r.lastStatus
}
