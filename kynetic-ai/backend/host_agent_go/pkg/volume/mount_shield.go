package volume

import (
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
)

// MountShieldConfig holds mount namespace sandbox parameters
type MountShieldConfig struct {
	InstanceID    string `json:"instance_id"`
	SandboxRootDir string `json:"sandbox_root_dir"`
	EphemeralDir  string `json:"ephemeral_dir"`
}

// MountShieldManager manages private mount namespaces and unshared storage air-gapping
type MountShieldManager struct {
	Config MountShieldConfig
}

// NewMountShieldManager initializes mount air-gapping for an instance
func NewMountShieldManager(instanceID, baseDir string) *MountShieldManager {
	if baseDir == "" {
		baseDir = "/var/lib/kynetic/sandboxes"
	}
	return &MountShieldManager{
		Config: MountShieldConfig{
			InstanceID:    instanceID,
			SandboxRootDir: filepath.Join(baseDir, instanceID),
			EphemeralDir:  filepath.Join(baseDir, instanceID, "scratch"),
		},
	}
}

// PrepareSandboxLayout creates private ephemeral directories and verifies host isolation
func (m *MountShieldManager) PrepareSandboxLayout() error {
	if err := os.MkdirAll(m.Config.EphemeralDir, 0700); err != nil {
		return fmt.Errorf("failed to create ephemeral sandbox dir: %w", err)
	}

	// Verify host home directory is not accessible inside sandbox root
	homeDir, _ := os.UserHomeDir()
	if homeDir != "" {
		leakedPath := filepath.Join(m.Config.SandboxRootDir, filepath.Base(homeDir))
		if _, err := os.Stat(leakedPath); err == nil {
			return fmt.Errorf("security violation: host home directory visible in sandbox at %s", leakedPath)
		}
	}

	return nil
}

// CleanupSandbox destroys all ephemeral sandbox directories and temporary mounts
func (m *MountShieldManager) CleanupSandbox() error {
	// Unmount any active bind mounts recursively
	cmd := exec.Command("umount", "-R", m.Config.SandboxRootDir)
	_ = cmd.Run()

	return os.RemoveAll(m.Config.SandboxRootDir)
}
