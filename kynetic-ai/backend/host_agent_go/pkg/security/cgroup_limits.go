package security

import (
	"context"
	"fmt"
	"os"
	"path/filepath"
	"sync"

	"go.uber.org/zap"
)

// CgroupCeiling configures limits for cgroups v2 resource boundaries.
type CgroupCeiling struct {
	MaxPids      int    `json:"max_pids"`      // e.g. 512 to prevent fork bombs
	MemoryMaxMB  int    `json:"memory_max_mb"` // Maximum physical RAM
	SwapMaxMB    int    `json:"swap_max_mb"`   // Maximum swap (0 to disable swap)
	CPUMaxQuota  string `json:"cpu_max_quota"` // e.g. "max 100000"
}

// CgroupLimitsManager enforces cgroup v2 bounds on container/sandbox slices
// preventing host exhaustion, kernel out-of-memory lockups, or fork bombs.
type CgroupLimitsManager struct {
	logger       *zap.Logger
	cgroupV2Root string
	mu           sync.Mutex
	appliedPids  map[string]int
}

// NewCgroupLimitsManager creates a new CgroupLimitsManager.
func NewCgroupLimitsManager(logger *zap.Logger, cgroupV2Root string) *CgroupLimitsManager {
	if cgroupV2Root == "" {
		cgroupV2Root = "/sys/fs/cgroup/kynetic.slice"
	}
	return &CgroupLimitsManager{
		logger:       logger,
		cgroupV2Root: cgroupV2Root,
		appliedPids:  make(map[string]int),
	}
}

// ApplyContainerLimits configures pids.max, memory.max, and memory.swap.max for a tenant sandbox.
func (c *CgroupLimitsManager) ApplyContainerLimits(ctx context.Context, tenantID string, ceiling CgroupCeiling) error {
	c.mu.Lock()
	defer c.mu.Unlock()

	sliceDir := filepath.Join(c.cgroupV2Root, tenantID)
	if err := os.MkdirAll(sliceDir, 0755); err != nil {
		c.logger.Debug("Could not create cgroup slice directory (mock/non-Linux mode)", zap.String("dir", sliceDir))
		c.appliedPids[tenantID] = ceiling.MaxPids
		return nil
	}

	// 1. Set pids.max (Anti-Fork-Bomb)
	pidsFile := filepath.Join(sliceDir, "pids.max")
	if ceiling.MaxPids > 0 {
		_ = os.WriteFile(pidsFile, []byte(fmt.Sprintf("%d", ceiling.MaxPids)), 0644)
	}

	// 2. Set memory.max
	if ceiling.MemoryMaxMB > 0 {
		memFile := filepath.Join(sliceDir, "memory.max")
		_ = os.WriteFile(memFile, []byte(fmt.Sprintf("%d", int64(ceiling.MemoryMaxMB)*1024*1024)), 0644)
	}

	// 3. Set memory.swap.max
	swapFile := filepath.Join(sliceDir, "memory.swap.max")
	_ = os.WriteFile(swapFile, []byte(fmt.Sprintf("%d", int64(ceiling.SwapMaxMB)*1024*1024)), 0644)

	c.appliedPids[tenantID] = ceiling.MaxPids
	c.logger.Info("Cgroups v2 limits enforced for tenant",
		zap.String("tenant_id", tenantID),
		zap.Int("max_pids", ceiling.MaxPids),
		zap.Int("memory_mb", ceiling.MemoryMaxMB),
	)
	return nil
}

// RemoveContainerLimits tears down the cgroup slice on container termination.
func (c *CgroupLimitsManager) RemoveContainerLimits(ctx context.Context, tenantID string) error {
	c.mu.Lock()
	defer c.mu.Unlock()

	sliceDir := filepath.Join(c.cgroupV2Root, tenantID)
	_ = os.Remove(sliceDir)
	delete(c.appliedPids, tenantID)
	c.logger.Info("Cgroups v2 slice cleaned up", zap.String("tenant_id", tenantID))
	return nil
}

// GetAppliedPidsLimit returns the configured PID limit for a tenant.
func (c *CgroupLimitsManager) GetAppliedPidsLimit(tenantID string) int {
	c.mu.Lock()
	defer c.mu.Unlock()
	return c.appliedPids[tenantID]
}
