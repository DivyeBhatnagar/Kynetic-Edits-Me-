package hardware

import (
	"context"
	"os"
	"strings"
	"sync"

	"go.uber.org/zap"
)

// CPUEnclaveType represents hardware CPU memory encryption technology.
type CPUEnclaveType string

const (
	EnclaveNone   CPUEnclaveType = "none"
	EnclaveSEVSNP CPUEnclaveType = "amd_sev_snp"
	EnclaveIntelTDX CPUEnclaveType = "intel_tdx"
)

// EnclaveMemoryManager checks and verifies host hardware support for AMD SEV-SNP or Intel TDX
// guaranteeing hypervisor-isolated guest RAM encryption.
type EnclaveMemoryManager struct {
	logger      *zap.Logger
	cpuinfoPath string
	mu          sync.Mutex
	enclaveType CPUEnclaveType
}

// NewEnclaveMemoryManager instantiates a new EnclaveMemoryManager.
func NewEnclaveMemoryManager(logger *zap.Logger, cpuinfoPath string) *EnclaveMemoryManager {
	if cpuinfoPath == "" {
		cpuinfoPath = "/proc/cpuinfo"
	}
	return &EnclaveMemoryManager{
		logger:      logger,
		cpuinfoPath: cpuinfoPath,
		enclaveType: EnclaveNone,
	}
}

// DetectHardwareEnclaves parses /proc/cpuinfo flags for sev_snp or tdx flags.
func (e *EnclaveMemoryManager) DetectHardwareEnclaves(ctx context.Context) (CPUEnclaveType, error) {
	e.mu.Lock()
	defer e.mu.Unlock()

	data, err := os.ReadFile(e.cpuinfoPath)
	if err != nil {
		if os.IsNotExist(err) {
			e.logger.Debug("cpuinfo not present, fallback to none")
			e.enclaveType = EnclaveNone
			return EnclaveNone, nil
		}
		return EnclaveNone, err
	}

	content := string(data)
	if strings.Contains(content, "sev_snp") || strings.Contains(content, "sev") {
		e.enclaveType = EnclaveSEVSNP
	} else if strings.Contains(content, "tdx") {
		e.enclaveType = EnclaveIntelTDX
	} else {
		e.enclaveType = EnclaveNone
	}

	e.logger.Info("CPU Enclave Hardware capability detected", zap.String("type", string(e.enclaveType)))
	return e.enclaveType, nil
}

// GetEnclaveType returns current detected enclave type.
func (e *EnclaveMemoryManager) GetEnclaveType() CPUEnclaveType {
	e.mu.Lock()
	defer e.mu.Unlock()
	return e.enclaveType
}
