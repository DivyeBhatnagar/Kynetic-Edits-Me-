package hardware

import (
	"fmt"
	"sync"
)

// DDIOCacheShield monitors PCIe Direct Data I/O (DDIO) L3 cache allocations
// and detects stealth cache eviction attacks targeting tenant CPU cores.
type DDIOCacheShield struct {
	mu                    sync.Mutex
	maxDDIOOccupancyWays  uint8 // Default 2 ways (out of 11/16 L3 ways)
	currentOccupancyWays  uint8
	ddioThrottlingEnabled bool
	evictionAlerts        []string
}

// NewDDIOCacheShield initializes a DDIO cache eviction protector.
func NewDDIOCacheShield(maxWays uint8) *DDIOCacheShield {
	return &DDIOCacheShield{
		maxDDIOOccupancyWays:  maxWays,
		currentOccupancyWays:  2,
		ddioThrottlingEnabled: false,
		evictionAlerts:        make([]string, 0),
	}
}

// AuditDDIOUsage evaluates PCIe DMA write saturation on the shared L3 Last-Level Cache.
func (d *DDIOCacheShield) AuditDDIOUsage(requestedWays uint8) (bool, string) {
	d.mu.Lock()
	defer d.mu.Unlock()

	d.currentOccupancyWays = requestedWays

	if requestedWays > d.maxDDIOOccupancyWays {
		d.ddioThrottlingEnabled = true
		alert := fmt.Sprintf("DDIO_STEALTH_CACHE_EVICTION_ATTACK: PCIe device occupying %d L3 cache ways > ceiling %d", requestedWays, d.maxDDIOOccupancyWays)
		d.evictionAlerts = append(d.evictionAlerts, alert)
		return false, alert
	}

	d.ddioThrottlingEnabled = false
	return true, "DDIO_CACHE_OCCUPANCY_SAFE"
}
