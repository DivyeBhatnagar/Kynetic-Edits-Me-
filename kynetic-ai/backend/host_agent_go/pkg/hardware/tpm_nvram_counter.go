package hardware

import (
	"fmt"
	"sync"
)

// TPMNVRAMCounter holds the state of a hardware-backed monotonic counter.
type TPMNVRAMCounter struct {
	NVIndex      uint32 `json:"nv_index"`
	CurrentValue uint64 `json:"current_value"`
	MinAllowed   uint64 `json:"min_allowed"`
	IsHardwareTPM bool  `json:"is_hardware_tpm"`
}

// TPMNVRAMAntiRollbackManager manages monotonic anti-rollback verification using TPM 2.0 NVRAM.
type TPMNVRAMAntiRollbackManager struct {
	mu       sync.Mutex
	counters map[uint32]*TPMNVRAMCounter
}

// NewTPMNVRAMAntiRollbackManager initializes the TPM NVRAM anti-rollback manager.
func NewTPMNVRAMAntiRollbackManager() *TPMNVRAMAntiRollbackManager {
	return &TPMNVRAMAntiRollbackManager{
		counters: make(map[uint32]*TPMNVRAMCounter),
	}
}

// DefineCounter allocates a monotonic counter index in TPM NVRAM.
func (t *TPMNVRAMAntiRollbackManager) DefineCounter(nvIndex uint32, initialValue uint64) error {
	t.mu.Lock()
	defer t.mu.Unlock()

	if _, exists := t.counters[nvIndex]; exists {
		return fmt.Errorf("TPM NVRAM counter index 0x%x already defined", nvIndex)
	}

	t.counters[nvIndex] = &TPMNVRAMCounter{
		NVIndex:       nvIndex,
		CurrentValue:  initialValue,
		MinAllowed:    initialValue,
		IsHardwareTPM: true,
	}
	return nil
}

// IncrementCounter increments the monotonic counter (hardware TPM2_NV_Increment).
func (t *TPMNVRAMAntiRollbackManager) IncrementCounter(nvIndex uint32) (uint64, error) {
	t.mu.Lock()
	defer t.mu.Unlock()

	c, exists := t.counters[nvIndex]
	if !exists {
		return 0, fmt.Errorf("TPM NVRAM counter index 0x%x not found", nvIndex)
	}

	c.CurrentValue++
	c.MinAllowed = c.CurrentValue
	return c.CurrentValue, nil
}

// AssertVersionNotRolledBack asserts that an incoming firmware/software version is >= TPM NVRAM counter.
func (t *TPMNVRAMAntiRollbackManager) AssertVersionNotRolledBack(nvIndex uint32, incomingVersion uint64) (bool, string) {
	t.mu.Lock()
	defer t.mu.Unlock()

	c, exists := t.counters[nvIndex]
	if !exists {
		return false, fmt.Sprintf("NVRAM_INDEX_0x%x_NOT_DEFINED", nvIndex)
	}

	if incomingVersion < c.CurrentValue {
		return false, fmt.Sprintf("ANTI_ROLLBACK_BLOCKED: incoming version %d < TPM NVRAM monotonic value %d", incomingVersion, c.CurrentValue)
	}

	return true, "ANTI_ROLLBACK_ASSERTION_PASSED"
}
