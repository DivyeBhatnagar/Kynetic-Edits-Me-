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

// AERReport represents PCIe Advanced Error Reporting status for host interconnects.
type AERReport struct {
	CorrectableErrors   uint64 `json:"correctable_errors"`
	UncorrectableErrors uint64 `json:"uncorrectable_errors"`
	PoisonedTLPDetected bool   `json:"poisoned_tlp_detected"`
}

// PCIeTLPGuard monitors PCIe Advanced Error Reporting (AER) sysfs telemetry for
// malformed or poisoned Transaction Layer Packets (TLP) indicating hardware fuzzing.
type PCIeTLPGuard struct {
	logger     *zap.Logger
	sysPciPath string
	mu         sync.Mutex
	lastReport AERReport
}

// NewPCIeTLPGuard creates a new PCIeTLPGuard.
func NewPCIeTLPGuard(logger *zap.Logger, sysPciPath string) *PCIeTLPGuard {
	if sysPciPath == "" {
		sysPciPath = "/sys/bus/pci/devices"
	}
	return &PCIeTLPGuard{
		logger:     logger,
		sysPciPath: sysPciPath,
	}
}

// AuditAERStatus scans all PCIe devices for AER error status nodes.
func (p *PCIeTLPGuard) AuditAERStatus(ctx context.Context) (AERReport, error) {
	p.mu.Lock()
	defer p.mu.Unlock()

	report := AERReport{}
	entries, err := os.ReadDir(p.sysPciPath)
	if err != nil {
		if os.IsNotExist(err) {
			p.logger.Debug("PCIe sysfs path not present (mock/fallback mode)")
			p.lastReport = report
			return report, nil
		}
		return report, err
	}

	for _, entry := range entries {
		aerDevPath := filepath.Join(p.sysPciPath, entry.Name(), "aer_dev_correctable")
		if data, err := os.ReadFile(aerDevPath); err == nil {
			val, _ := strconv.ParseUint(strings.TrimSpace(string(data)), 10, 64)
			report.CorrectableErrors += val
		}

		aerFatalPath := filepath.Join(p.sysPciPath, entry.Name(), "aer_dev_fatal")
		if data, err := os.ReadFile(aerFatalPath); err == nil {
			val, _ := strconv.ParseUint(strings.TrimSpace(string(data)), 10, 64)
			report.UncorrectableErrors += val
			if val > 0 {
				report.PoisonedTLPDetected = true
			}
		}
	}

	p.lastReport = report
	return report, nil
}

// GetLastReport returns the most recent AER report.
func (p *PCIeTLPGuard) GetLastReport() AERReport {
	p.mu.Lock()
	defer p.mu.Unlock()
	return p.lastReport
}
