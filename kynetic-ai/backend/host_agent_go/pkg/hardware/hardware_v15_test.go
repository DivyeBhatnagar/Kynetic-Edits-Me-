package hardware

import (
	"testing"
	"time"
)

func TestPowerSlewTrap(t *testing.T) {
	cfg := DefaultPowerSlewConfig()
	trap := NewPowerSlewTrap(cfg)

	// Calibration tick
	tripped, msg := trap.IngestTelemetry(PowerSlewSample{
		TimestampMicrosec: 1000,
		VoltageVolts:      12.0,
		CurrentAmps:       10.0,
	})
	if tripped {
		t.Fatalf("first sample should calibrate: %s", msg)
	}

	// Normal benign delta
	tripped, msg = trap.IngestTelemetry(PowerSlewSample{
		TimestampMicrosec: 1010,
		VoltageVolts:      11.99,
		CurrentAmps:       10.5,
	})
	if tripped {
		t.Fatalf("benign delta should not trip: %s", msg)
	}

	// Massive voltage droop (EMFI attack simulation: 1.5V drop in 2 microseconds = 0.75 V/us > 0.05)
	tripped, msg = trap.IngestTelemetry(PowerSlewSample{
		TimestampMicrosec: 1012,
		VoltageVolts:      10.49,
		CurrentAmps:       10.5,
	})
	if !tripped {
		t.Fatalf("expected EMFI voltage glitch tripwire to trigger, got %s", msg)
	}
	if !trap.IsTripped() {
		t.Fatalf("trap should be marked tripped")
	}
}

func TestDDR5MSKRotator(t *testing.T) {
	rotator := NewDDR5MSKRotator(5 * time.Minute)
	key1, err := rotator.GetActiveKey()
	if err != nil {
		t.Fatalf("failed to get active key: %v", err)
	}
	if key1.KeyEpoch != 1 {
		t.Fatalf("expected epoch 1, got %d", key1.KeyEpoch)
	}

	err = rotator.RotateScramblingKey()
	if err != nil {
		t.Fatalf("failed to rotate key: %v", err)
	}

	key2, _ := rotator.GetActiveKey()
	if key2.KeyEpoch != 2 || key2.KeyHex == key1.KeyHex {
		t.Fatalf("key rotation failed to generate fresh distinct epoch/key")
	}
}

func TestDMABoundsEnforcer(t *testing.T) {
	enforcer := NewDMABoundsEnforcer(0x100000, 0x200000, 10) // 1MB - 2MB window

	validTable := []DMAScatterGatherDescriptor{
		{PhysicalAddress: 0x100000, LengthBytes: 0x1000},
		{PhysicalAddress: 0x150000, LengthBytes: 0x2000},
	}
	ok, msg := enforcer.ValidateScatterGatherTable(validTable)
	if !ok {
		t.Fatalf("valid DMA table rejected: %s", msg)
	}

	// Out of bounds DMA attempt
	badTable := []DMAScatterGatherDescriptor{
		{PhysicalAddress: 0x250000, LengthBytes: 0x1000},
	}
	ok2, msg2 := enforcer.ValidateScatterGatherTable(badTable)
	if ok2 {
		t.Fatalf("out-of-bounds DMA was allowed: %s", msg2)
	}
}

func TestTPMNVRAMAntiRollback(t *testing.T) {
	mgr := NewTPMNVRAMAntiRollbackManager()
	nvIndex := uint32(0x1500001)

	err := mgr.DefineCounter(nvIndex, 100)
	if err != nil {
		t.Fatalf("failed to define counter: %v", err)
	}

	// Assert version 100 passes
	ok, msg := mgr.AssertVersionNotRolledBack(nvIndex, 100)
	if !ok {
		t.Fatalf("version 100 should pass: %s", msg)
	}

	// Increment to 101
	newVal, _ := mgr.IncrementCounter(nvIndex)
	if newVal != 101 {
		t.Fatalf("expected 101, got %d", newVal)
	}

	// Assert version 100 is now rejected (rollback blocked)
	ok2, msg2 := mgr.AssertVersionNotRolledBack(nvIndex, 100)
	if ok2 {
		t.Fatalf("version 100 rollback should be blocked: %s", msg2)
	}
}
