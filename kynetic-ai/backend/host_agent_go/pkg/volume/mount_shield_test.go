package volume_test

import (
	"os"
	"testing"

	"github.com/kynetic-ai/host-agent/pkg/volume"
)

func TestMountShieldManager(t *testing.T) {
	tmpDir, err := os.MkdirTemp("", "kynetic_sandbox_test_*")
	if err != nil {
		t.Fatalf("failed to create temp dir: %v", err)
	}
	defer os.RemoveAll(tmpDir)

	mgr := volume.NewMountShieldManager("inst-test-12345678", tmpDir)
	if err := mgr.PrepareSandboxLayout(); err != nil {
		t.Fatalf("failed to prepare sandbox layout: %v", err)
	}

	if err := mgr.CleanupSandbox(); err != nil {
		t.Fatalf("failed to cleanup sandbox: %v", err)
	}
}
