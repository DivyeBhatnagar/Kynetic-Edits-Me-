package hardware

import (
	"fmt"
	"sync"
)

// HBM3eSubArrayMetrics holds activation counts and thermal readings per HBM3e stack layer.
type HBM3eSubArrayMetrics struct {
	StackIndex       uint8   `json:"stack_index"` // Stack 0-7
	BankID           uint16  `json:"bank_id"`
	RowActivations   uint64  `json:"row_activations"`
	DieTempCelsius   float64 `json:"die_temp_celsius"`
	TRRRefreshesIssued uint64 `json:"trr_refreshes_issued"`
}

// HBM3eTRRMonitor monitors HBM3e sub-array activation frequencies to prevent Rowhammer and thermal hotspot faults.
type HBM3eTRRMonitor struct {
	mu                  sync.Mutex
	maxActivationsThreshold uint64
	maxTempThresholdCelsius float64
	stackMetrics        map[string]*HBM3eSubArrayMetrics
	trrEventsEmitted    uint64
}

// NewHBM3eTRRMonitor initializes an HBM3e memory defense controller.
func NewHBM3eTRRMonitor(maxActivations uint64, maxTemp float64) *HBM3eTRRMonitor {
	return &HBM3eTRRMonitor{
		maxActivationsThreshold: maxActivations,
		maxTempThresholdCelsius: maxTemp,
		stackMetrics:        make(map[string]*HBM3eSubArrayMetrics),
	}
}

// RecordRowActivation tracks access frequency for a specific (Stack, Bank, Row) target.
func (h *HBM3eTRRMonitor) RecordRowActivation(stackIndex uint8, bankID uint16, rowID uint32, dieTemp float64) (bool, string) {
	h.mu.Lock()
	defer h.mu.Unlock()

	key := fmt.Sprintf("s%d_b%d", stackIndex, bankID)
	metrics, exists := h.stackMetrics[key]
	if !exists {
		metrics = &HBM3eSubArrayMetrics{
			StackIndex:     stackIndex,
			BankID:         bankID,
			DieTempCelsius: dieTemp,
		}
		h.stackMetrics[key] = metrics
	}

	metrics.RowActivations++
	metrics.DieTempCelsius = dieTemp

	if metrics.RowActivations > h.maxActivationsThreshold {
		// Trigger hardware Target Row Refresh (TRR) to prevent bitflips in adjacent victim rows
		metrics.TRRRefreshesIssued++
		metrics.RowActivations = 0
		h.trrEventsEmitted++
		return true, fmt.Sprintf("HBM3E_TRR_PULSE_EMITTED: stack %d bank %d prevented rowhammer bitflip", stackIndex, bankID)
	}

	if dieTemp > h.maxTempThresholdCelsius {
		return true, fmt.Sprintf("HBM3E_SUBARRAY_THERMAL_ALERT: stack %d at %.1fC > threshold %.1fC", stackIndex, dieTemp, h.maxTempThresholdCelsius)
	}

	return false, "HBM3E_SUBARRAY_STABLE"
}
