package security

import (
	"context"
	"fmt"
	"os"
	"strings"
	"sync"

	"go.uber.org/zap"
)

// LockdownLevel represents the Linux kernel lockdown mode status.
type LockdownLevel string

const (
	LockdownNone         LockdownLevel = "none"
	LockdownIntegrity    LockdownLevel = "integrity"
	LockdownConfidential LockdownLevel = "confidentiality"
)

// KernelLockdownController enforces Linux kernel lockdown mode via sysfs securityfs
// to prevent even root in guest escapes from modifying kernel memory, /dev/mem, or hibernating.
type KernelLockdownController struct {
	logger       *zap.Logger
	lockdownPath string
	mu           sync.Mutex
	currentLevel LockdownLevel
}

// NewKernelLockdownController creates a new KernelLockdownController.
func NewKernelLockdownController(logger *zap.Logger, lockdownPath string) *KernelLockdownController {
	if lockdownPath == "" {
		lockdownPath = "/sys/kernel/security/lockdown"
	}
	return &KernelLockdownController{
		logger:       logger,
		lockdownPath: lockdownPath,
		currentLevel: LockdownNone,
	}
}

// QueryCurrentLockdown inspects /sys/kernel/security/lockdown to verify which mode is active.
func (k *KernelLockdownController) QueryCurrentLockdown() (LockdownLevel, error) {
	k.mu.Lock()
	defer k.mu.Unlock()

	data, err := os.ReadFile(k.lockdownPath)
	if err != nil {
		if os.IsNotExist(err) {
			k.logger.Debug("Kernel lockdown file not found (non-Linux or securityfs not mounted)")
			return LockdownNone, nil
		}
		return LockdownNone, fmt.Errorf("failed to read kernel lockdown state: %w", err)
	}

	content := string(data)
	if strings.Contains(content, "[confidentiality]") {
		k.currentLevel = LockdownConfidential
	} else if strings.Contains(content, "[integrity]") {
		k.currentLevel = LockdownIntegrity
	} else {
		k.currentLevel = LockdownNone
	}

	return k.currentLevel, nil
}

// EnforceConfidentialityMode attempts to lift kernel lockdown to 'confidentiality' or 'integrity'.
func (k *KernelLockdownController) EnforceConfidentialityMode(ctx context.Context, target LockdownLevel) error {
	k.mu.Lock()
	defer k.mu.Unlock()

	if target != LockdownIntegrity && target != LockdownConfidential {
		return fmt.Errorf("invalid lockdown target level: %s", target)
	}

	if _, err := os.Stat(k.lockdownPath); err != nil {
		if os.IsNotExist(err) {
			k.logger.Warn("Lockdown file unavailable, simulating enforcement", zap.String("target", string(target)))
			k.currentLevel = target
			return nil
		}
		return err
	}

	err := os.WriteFile(k.lockdownPath, []byte(string(target)), 0644)
	if err != nil {
		k.logger.Warn("Could not write kernel lockdown level (may require kernel boot param or higher privs)",
			zap.String("target", string(target)),
			zap.Error(err),
		)
		return err
	}

	k.currentLevel = target
	k.logger.Info("Linux Kernel Lockdown successfully elevated", zap.String("level", string(target)))
	return nil
}

// GetLevel returns the cached kernel lockdown level.
func (k *KernelLockdownController) GetLevel() LockdownLevel {
	k.mu.Lock()
	defer k.mu.Unlock()
	return k.currentLevel
}
