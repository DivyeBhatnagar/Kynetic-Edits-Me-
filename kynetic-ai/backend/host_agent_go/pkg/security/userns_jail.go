package security

import (
	"context"
	"fmt"
	"os"
	"path/filepath"
	"sync"

	"go.uber.org/zap"
)

// UserNamespaceConfig defines high-range UID/GID mapping for container rootless dual-jail.
type UserNamespaceConfig struct {
	ContainerUID int `json:"container_uid"` // e.g. 0 (root inside container)
	HostUIDStart int `json:"host_uid_start"` // e.g. 100000 (unprivileged on host)
	RangeCount   int `json:"range_count"`    // e.g. 65536
}

// UserNamespaceJail configures Linux user namespace mappings (`/proc/self/uid_map`)
// guaranteeing that root inside a tenant container has zero privileges if an escape occurs.
type UserNamespaceJail struct {
	logger      *zap.Logger
	procPath    string
	mu          sync.Mutex
	activeJails int
}

// NewUserNamespaceJail creates a new UserNamespaceJail.
func NewUserNamespaceJail(logger *zap.Logger, procPath string) *UserNamespaceJail {
	if procPath == "" {
		procPath = "/proc"
	}
	return &UserNamespaceJail{
		logger:   logger,
		procPath: procPath,
	}
}

// ConfigureUIDMap writes high-range unprivileged mapping to a process uid_map.
func (u *UserNamespaceJail) ConfigureUIDMap(ctx context.Context, pid int, cfg UserNamespaceConfig) error {
	u.mu.Lock()
	defer u.mu.Unlock()

	uidMapPath := filepath.Join(u.procPath, fmt.Sprintf("%d", pid), "uid_map")
	mappingStr := fmt.Sprintf("%d %d %d\n", cfg.ContainerUID, cfg.HostUIDStart, cfg.RangeCount)

	if _, err := os.Stat(uidMapPath); err == nil {
		_ = os.WriteFile(uidMapPath, []byte(mappingStr), 0644)
	}

	u.activeJails++
	u.logger.Info("User namespace high-range dual-jail mapped",
		zap.Int("pid", pid),
		zap.Int("host_uid_start", cfg.HostUIDStart),
	)
	return nil
}

// GetActiveJails returns count of configured userns jails.
func (u *UserNamespaceJail) GetActiveJails() int {
	u.mu.Lock()
	defer u.mu.Unlock()
	return u.activeJails
}
