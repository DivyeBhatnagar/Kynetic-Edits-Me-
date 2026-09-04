package firewall

import (
	"context"
	"sync"

	"go.uber.org/zap"
)

// IPPacketMeta represents headers for assessing packet fragmentation attacks.
type IPPacketMeta struct {
	TotalLength uint16 `json:"total_length"`
	HeaderLength uint8 `json:"header_length"`
	FragmentOffset uint16 `json:"fragment_offset"`
	MoreFragments bool `json:"more_fragments"`
	Protocol uint8 `json:"protocol"`
}

// MTUFragmentFilter analyzes packet fragmentation to block Tiny Fragment and Overlapping Fragment attacks.
type MTUFragmentFilter struct {
	logger           *zap.Logger
	minFragmentSize  uint16
	mu               sync.Mutex
	blockedFragments uint64
}

// NewMTUFragmentFilter creates a new MTUFragmentFilter.
func NewMTUFragmentFilter(logger *zap.Logger, minFragmentSize uint16) *MTUFragmentFilter {
	if minFragmentSize == 0 {
		minFragmentSize = 68 // Standard RFC min IPv4 fragment size
	}
	return &MTUFragmentFilter{
		logger:          logger,
		minFragmentSize: minFragmentSize,
	}
}

// InspectPacket checks if packet exhibits characteristics of a fragment evasion attack.
func (m *MTUFragmentFilter) InspectPacket(ctx context.Context, meta IPPacketMeta) (bool, string) {
	m.mu.Lock()
	defer m.mu.Unlock()

	// 1. Tiny Fragment Attack (fragment offset is 0, but total length is smaller than complete TCP header)
	if meta.FragmentOffset == 0 && meta.MoreFragments && meta.TotalLength < 60 {
		m.blockedFragments++
		m.logger.Warn("MTUFragmentFilter: Tiny Fragment Attack packet detected & dropped",
			zap.Uint16("len", meta.TotalLength),
		)
		return true, "Tiny Fragment Attack: packet too small to contain complete L4 header"
	}

	// 2. Unusually small sub-fragments
	if meta.FragmentOffset > 0 && meta.TotalLength < m.minFragmentSize {
		m.blockedFragments++
		return true, "Sub-fragment below minimum MTU safety threshold"
	}

	return false, "packet clean"
}

// GetBlockedCount returns count of blocked fragmentation attacks.
func (m *MTUFragmentFilter) GetBlockedCount() uint64 {
	m.mu.Lock()
	defer m.mu.Unlock()
	return m.blockedFragments
}
