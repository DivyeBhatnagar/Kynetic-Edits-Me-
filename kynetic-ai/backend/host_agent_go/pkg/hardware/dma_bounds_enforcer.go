package hardware

import (
	"fmt"
	"sync"
)

// DMAScatterGatherDescriptor defines a physical memory DMA segment.
type DMAScatterGatherDescriptor struct {
	PhysicalAddress uint64 `json:"phys_addr"`
	LengthBytes     uint32 `json:"length_bytes"`
	Flags           uint16 `json:"flags"`
}

// DMABoundsEnforcer audits and restricts physical scatter-gather DMA descriptor chains.
type DMABoundsEnforcer struct {
	mu                   sync.Mutex
	allowedPhysBase      uint64
	allowedPhysLimit     uint64
	maxDescriptorEntries int
	violationsTrapped    uint64
}

// NewDMABoundsEnforcer constructs a new DMA scatter-gather validator.
func NewDMABoundsEnforcer(physBase, physLimit uint64, maxEntries int) *DMABoundsEnforcer {
	return &DMABoundsEnforcer{
		allowedPhysBase:      physBase,
		allowedPhysLimit:     physLimit,
		maxDescriptorEntries: maxEntries,
	}
}

// ValidateScatterGatherTable audits an incoming DMA list for boundary overflows or unauthorized physical memory access.
func (d *DMABoundsEnforcer) ValidateScatterGatherTable(descriptors []DMAScatterGatherDescriptor) (bool, string) {
	d.mu.Lock()
	defer d.mu.Unlock()

	if len(descriptors) > d.maxDescriptorEntries {
		d.violationsTrapped++
		return false, fmt.Sprintf("DMA_DESCRIPTOR_COUNT_EXCEEDED: %d > %d", len(descriptors), d.maxDescriptorEntries)
	}

	for i, desc := range descriptors {
		start := desc.PhysicalAddress
		end := start + uint64(desc.LengthBytes)

		// Check arithmetic overflow
		if end < start {
			d.violationsTrapped++
			return false, fmt.Sprintf("DMA_INTEGER_WRAPAROUND_AT_INDEX_%d: addr=0x%x len=0x%x", i, start, desc.LengthBytes)
		}

		// Check lower bound
		if start < d.allowedPhysBase {
			d.violationsTrapped++
			return false, fmt.Sprintf("DMA_UNDERFLOW_VIOLATION_AT_INDEX_%d: addr 0x%x < base 0x%x", i, start, d.allowedPhysBase)
		}

		// Check upper bound
		if end > d.allowedPhysLimit {
			d.violationsTrapped++
			return false, fmt.Sprintf("DMA_OVERFLOW_VIOLATION_AT_INDEX_%d: end 0x%x > limit 0x%x", i, end, d.allowedPhysLimit)
		}
	}

	return true, "DMA_SCATTER_GATHER_BUFFER_BOUNDS_VALID"
}
