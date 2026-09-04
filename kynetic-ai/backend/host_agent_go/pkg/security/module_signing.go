package security

import (
	"context"
	"os"
	"path/filepath"
	"strings"
	"sync"

	"go.uber.org/zap"
)

// ModuleSigningGuard enforces Linux kernel module signature verification (`module.sig_enforce = 1`)
// preventing rogue out-of-tree drivers from loading into host kernel space.
type ModuleSigningGuard struct {
	logger         *zap.Logger
	moduleSysPath  string
	mu             sync.Mutex
	sigEnforced    bool
}

// NewModuleSigningGuard creates a new ModuleSigningGuard.
func NewModuleSigningGuard(logger *zap.Logger, moduleSysPath string) *ModuleSigningGuard {
	if moduleSysPath == "" {
		moduleSysPath = "/sys/module/module/parameters"
	}
	return &ModuleSigningGuard{
		logger:        logger,
		moduleSysPath: moduleSysPath,
	}
}

// AuditModuleSigning checks if unsigned kernel modules are blocked by the kernel.
func (m *ModuleSigningGuard) AuditModuleSigning(ctx context.Context) (bool, error) {
	m.mu.Lock()
	defer m.mu.Unlock()

	sigEnforcePath := filepath.Join(m.moduleSysPath, "sig_enforce")
	data, err := os.ReadFile(sigEnforcePath)
	if err != nil {
		if os.IsNotExist(err) {
			m.logger.Debug("module sig_enforce sysfs node not found (mock/fallback mode)")
			m.sigEnforced = false
			return false, nil
		}
		return false, err
	}

	content := strings.TrimSpace(string(data))
	m.sigEnforced = (content == "Y" || content == "1")
	m.logger.Info("Kernel module signature enforcement audited", zap.Bool("enforced", m.sigEnforced))
	return m.sigEnforced, nil
}

// IsEnforced returns current enforcement status.
func (m *ModuleSigningGuard) IsEnforced() bool {
	m.mu.Lock()
	defer m.mu.Unlock()
	return m.sigEnforced
}
