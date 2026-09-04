package firewall

import (
	"fmt"
	"sync"
	"time"
)

// RoCEv2PFCFrame represents an 802.1Qbb Priority Flow Control (PFC) pause packet on RDMA ethernet.
type RoCEv2PFCFrame struct {
	PriorityClass uint8  `json:"priority_class"` // 0-7
	PauseDurationQuanta uint16 `json:"pause_duration_quanta"`
	SrcMAC        string `json:"src_mac"`
	TimestampMicrosec int64 `json:"timestamp_us"`
}

// RoCEPFCFilterConfig configures anti-deadlock rate limiting thresholds.
type RoCEPFCFilterConfig struct {
	MaxPauseFramesPerSec uint32 `json:"max_pause_frames_per_sec"` // e.g., > 5000 frames/sec indicates PFC storm attack
	MaxConsecutivePauseQuanta uint32 `json:"max_consecutive_pause_quanta"`
}

// DefaultRoCEPFCConfig returns default RDMA defense parameters.
func DefaultRoCEPFCConfig() RoCEPFCFilterConfig {
	return RoCEPFCFilterConfig{
		MaxPauseFramesPerSec:      5000,
		MaxConsecutivePauseQuanta: 65535,
	}
}

// RoCEPFCFilter guards GPU RDMA over Converged Ethernet against PFC pause storms and deadlock attacks.
type RoCEPFCFilter struct {
	mu             sync.Mutex
	config         RoCEPFCFilterConfig
	frameCounts    map[uint8]uint32 // priority_class -> frame count in current window
	lastWindowSec  int64
	quantaAccum    map[uint8]uint32
	isThrottled    map[uint8]bool
}

// NewRoCEPFCFilter creates a new RoCEv2 PFC flow filter.
func NewRoCEPFCFilter(cfg RoCEPFCFilterConfig) *RoCEPFCFilter {
	return &RoCEPFCFilter{
		config:        cfg,
		frameCounts:   make(map[uint8]uint32),
		quantaAccum:   make(map[uint8]uint32),
		isThrottled:   make(map[uint8]bool),
		lastWindowSec: time.Now().Unix(),
	}
}

// IngestPFCFrame processes incoming PFC flow control frames and suppresses malicious pause storms.
func (r *RoCEPFCFilter) IngestPFCFrame(frame RoCEv2PFCFrame) (bool, string) {
	r.mu.Lock()
	defer r.mu.Unlock()

	nowSec := time.Now().Unix()
	if nowSec != r.lastWindowSec {
		r.frameCounts = make(map[uint8]uint32)
		r.quantaAccum = make(map[uint8]uint32)
		r.lastWindowSec = nowSec
	}

	r.frameCounts[frame.PriorityClass]++
	r.quantaAccum[frame.PriorityClass] += uint32(frame.PauseDurationQuanta)

	if r.frameCounts[frame.PriorityClass] > r.config.MaxPauseFramesPerSec {
		r.isThrottled[frame.PriorityClass] = true
		return false, fmt.Sprintf("ROCE_PFC_PAUSE_STORM_FILTERED: priority %d exceeded rate limit %d frames/sec", frame.PriorityClass, r.config.MaxPauseFramesPerSec)
	}

	return true, "ROCE_PFC_FRAME_PERMITTED"
}
