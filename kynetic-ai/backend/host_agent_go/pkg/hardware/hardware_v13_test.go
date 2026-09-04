package hardware

import (
	"testing"
	"time"

	"go.uber.org/zap"
)

func TestPCIeTDISPGuard(t *testing.T) {
	logger := zap.NewNop()
	guard := NewPCIeTDISPGuard(logger, "")

	states, err := guard.AuditPCIeInterconnects()
	if err != nil {
		t.Fatalf("AuditPCIeInterconnects failed: %v", err)
	}
	if len(states) == 0 {
		t.Fatalf("expected at least one audited device state")
	}

	ok, err := guard.VerifyDeviceAttestation(states[0].DeviceBDF, []byte("master_key_12345678901234567890"), []byte("golden_pcie_measurement"))
	if err != nil || !ok {
		t.Fatalf("VerifyDeviceAttestation failed: %v", err)
	}
}

func TestDMAFaultThrottler(t *testing.T) {
	logger := zap.NewNop()
	throttler := NewDMAFaultThrottler(logger, 2, 4, 100*time.Millisecond)

	bdf := "0000:03:00.0"

	// 1st fault -> normal
	ev, err := throttler.RecordDMAFault(bdf, 0x1000, "read_unmapped")
	if err != nil || ev.Throttled {
		t.Fatalf("1st fault should not throttle")
	}

	// 2nd fault -> throttled
	ev, err = throttler.RecordDMAFault(bdf, 0x2000, "read_unmapped")
	if err != nil || !ev.Throttled {
		t.Fatalf("2nd fault should throttle")
	}

	// 3rd fault -> throttled
	_, _ = throttler.RecordDMAFault(bdf, 0x3000, "read_unmapped")

	// 4th fault -> poisoned
	ev, err = throttler.RecordDMAFault(bdf, 0x4000, "read_unmapped")
	if err == nil || !ev.Poisoned {
		t.Fatalf("4th fault should trigger poison trap")
	}

	if !throttler.IsDevicePoisoned(bdf) {
		t.Fatalf("device should be marked poisoned")
	}
}

func TestCXLMemoryGuard(t *testing.T) {
	logger := zap.NewNop()
	guard := NewCXLMemoryGuard(logger, "")

	devices, err := guard.AuditCXLTopology()
	if err != nil {
		t.Fatalf("AuditCXLTopology failed: %v", err)
	}
	if len(devices) == 0 {
		t.Fatalf("expected at least one CXL device")
	}
	if !devices[0].IDEActive {
		t.Fatalf("expected CXL IDE to be active")
	}

	ok, err := guard.VerifyCXLSPDMAttestation(devices[0].DeviceID, []byte("cxl_rot_secret_key_32bytes_long"), []byte("spdm_quote_data"))
	if err != nil || !ok {
		t.Fatalf("VerifyCXLSPDMAttestation failed: %v", err)
	}
}
