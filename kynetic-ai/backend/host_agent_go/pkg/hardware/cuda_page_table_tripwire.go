package hardware

import (
	"fmt"
	"sync"
)

// CUDAPageMapping represents a virtual-to-physical VRAM page entry.
type CUDAPageMapping struct {
	VirtualAddress  uint64 `json:"virtual_address"`
	PhysicalAddress uint64 `json:"physical_address"`
	Flags           uint32 `json:"flags"`
	IsProtected     bool   `json:"is_protected"`
}

// CUDAPageTableTripwire audits CUDA VRAM memory page mappings and detects host driver remap attacks.
type CUDAPageTableTripwire struct {
	mu           sync.Mutex
	pageTable    map[uint64]CUDAPageMapping
	alerts       []string
	tripwireTripped bool
}

// NewCUDAPageTableTripwire initializes a CUDA shadow page-table tripwire.
func NewCUDAPageTableTripwire() *CUDAPageTableTripwire {
	return &CUDAPageTableTripwire{
		pageTable: make(map[uint64]CUDAPageMapping),
		alerts:    make([]string, 0),
	}
}

// RegisterProtectedPage maps a tenant VRAM page to its expected physical memory frame.
func (c *CUDAPageTableTripwire) RegisterProtectedPage(vAddr, pAddr uint64, flags uint32) {
	c.mu.Lock()
	defer c.mu.Unlock()

	c.pageTable[vAddr] = CUDAPageMapping{
		VirtualAddress:  vAddr,
		PhysicalAddress: pAddr,
		Flags:           flags,
		IsProtected:     true,
	}
}

// AuditDriverPageTableUpdate evaluates a page table modification submitted by the NVIDIA kernel driver.
func (c *CUDAPageTableTripwire) AuditDriverPageTableUpdate(vAddr, newPAddr uint64) (bool, string) {
	c.mu.Lock()
	defer c.mu.Unlock()

	mapping, exists := c.pageTable[vAddr]
	if !exists {
		return true, "NEW_PAGE_ALLOCATION_PERMITTED"
	}

	if mapping.IsProtected && mapping.PhysicalAddress != newPAddr {
		c.tripwireTripped = true
		alert := fmt.Sprintf("HOST_GPU_DRIVER_VRAM_REMAP_HIJACK_DETECTED: vAddr 0x%x remapped from 0x%x to 0x%x", vAddr, mapping.PhysicalAddress, newPAddr)
		c.alerts = append(c.alerts, alert)
		return false, alert
	}

	return true, "CUDA_PAGE_TABLE_MUTATION_AUTHORIZED"
}

// IsTripped returns true if an unauthenticated VRAM page remap occurred.
func (c *CUDAPageTableTripwire) IsTripped() bool {
	c.mu.Lock()
	defer c.mu.Unlock()
	return c.tripwireTripped
}
