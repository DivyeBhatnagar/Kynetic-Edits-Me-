package hardware

import (
	"testing"
)

func TestCollectManifest(t *testing.T) {
	manifest, err := CollectManifest()
	if err != nil {
		t.Fatalf("CollectManifest failed: %v", err)
	}

	t.Logf("Collected Hardware Manifest:")
	t.Logf("  CPU Model:   %s", manifest.CPUModel)
	t.Logf("  CPU Cores:   %d", manifest.CPUCores)
	t.Logf("  CPU Threads: %d", manifest.CPUThreads)
	t.Logf("  RAM GB:      %.2f GB", manifest.RAMgb)
	t.Logf("  Disk GB:     %.2f GB (%s)", manifest.DiskGB, manifest.DiskType)
	t.Logf("  GPU Count:   %d", len(manifest.GPUs))
	t.Logf("  OS Type:     %s", manifest.OSType)

	if manifest.CPUModel == "" {
		t.Errorf("expected non-empty CPUModel")
	}
	if manifest.CPUThreads <= 0 {
		t.Errorf("expected CPUThreads > 0, got %d", manifest.CPUThreads)
	}
	if manifest.OSType == "" {
		t.Errorf("expected non-empty OSType")
	}

	apiDict := manifest.ToAPIDict()
	if apiDict["cpu_model"] != manifest.CPUModel {
		t.Errorf("expected apiDict to contain cpu_model")
	}
}
