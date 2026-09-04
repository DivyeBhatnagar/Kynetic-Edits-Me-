package volume

import (
	"context"
	"testing"

	"go.uber.org/zap"
)

func TestNVMeCryptoEraser(t *testing.T) {
	logger, _ := zap.NewDevelopment()
	eraser := NewNVMeCryptoEraser(logger)

	// Test against simulated / mock device
	res, err := eraser.PerformCryptoErase(context.Background(), "/dev/nvme0n1")
	if err != nil {
		t.Fatalf("PerformCryptoErase returned unexpected error: %v", err)
	}

	if !res.Success {
		t.Errorf("expected crypto erase success to be true")
	}
	if res.DevicePath != "/dev/nvme0n1" {
		t.Errorf("expected device path /dev/nvme0n1, got %s", res.DevicePath)
	}
}
