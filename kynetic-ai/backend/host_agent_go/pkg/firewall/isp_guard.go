package firewall

import (
	"context"
	"fmt"
	"sync"
	"time"

	"go.uber.org/zap"
)

// TrafficStats captures real-time packets, bandwidth and potential abuse indicators.
type TrafficStats struct {
	OutboundPPS      uint64    `json:"outbound_pps"`
	OutboundBPS      uint64    `json:"outbound_bps"`
	SynPacketRate    uint32    `json:"syn_packet_rate"`
	UdpFloodCount    uint32    `json:"udp_flood_count"`
	BlacklistedPorts []int     `json:"blacklisted_ports"`
	LastAudited      time.Time `json:"last_audited"`
}

// ISPGuard monitors and polices outbound container traffic to prevent hosts from
// engaging in outbound DDoS, port scans, UDP reflection, or spamming, preventing ISP suspensions.
type ISPGuard struct {
	logger           *zap.Logger
	maxPPS           uint64
	maxBPS           uint64
	maxSynPerSec     uint32
	blockedPorts     map[int]bool
	mu               sync.Mutex
	currentStats     TrafficStats
	isThrottling     bool
	violationCounter uint32
}

// NewISPGuard constructs a new ISPGuard instance with default ISP-safe limits.
func NewISPGuard(logger *zap.Logger) *ISPGuard {
	// Standard ISP dangerous ports: 25 (SMTP Spam), 53 (DNS Amplification), 1900 (SSDP), 389 (CLDAP)
	blocked := map[int]bool{
		25:   true,
		53:   true,
		137:  true,
		138:  true,
		139:  true,
		445:  true,
		1900: true,
	}

	return &ISPGuard{
		logger:       logger,
		maxPPS:       50000,           // Max 50k packets per second
		maxBPS:       1000 * 1000 * 100, // 100 Mbps burst outbound limiter
		maxSynPerSec: 500,             // Max 500 SYN packets per second (anti-SYN scan)
		blockedPorts: blocked,
	}
}

// EvaluateTraffic checks whether the measured traffic profile violates ISP anti-abuse bounds.
func (g *ISPGuard) EvaluateTraffic(ctx context.Context, stats TrafficStats) (bool, string) {
	g.mu.Lock()
	defer g.mu.Unlock()

	g.currentStats = stats
	g.currentStats.LastAudited = time.Now()

	// 1. Check SYN scan flooding
	if stats.SynPacketRate > g.maxSynPerSec {
		g.violationCounter++
		g.isThrottling = true
		g.logger.Warn("ISPGuard: Detected potential outbound port scanning / SYN flood",
			zap.Uint32("syn_rate", stats.SynPacketRate),
			zap.Uint32("threshold", g.maxSynPerSec),
		)
		return true, fmt.Sprintf("SYN rate %d exceeds limit %d", stats.SynPacketRate, g.maxSynPerSec)
	}

	// 2. Check UDP / DDoS flooding PPS
	if stats.OutboundPPS > g.maxPPS {
		g.violationCounter++
		g.isThrottling = true
		g.logger.Warn("ISPGuard: Outbound PPS exceeds safety threshold",
			zap.Uint64("pps", stats.OutboundPPS),
			zap.Uint64("limit", g.maxPPS),
		)
		return true, fmt.Sprintf("Outbound PPS %d exceeds limit %d", stats.OutboundPPS, g.maxPPS)
	}

	// 3. Check blocked dangerous ports
	for _, port := range stats.BlacklistedPorts {
		if g.blockedPorts[port] {
			g.violationCounter++
			g.isThrottling = true
			g.logger.Warn("ISPGuard: Prohibited outbound port traffic detected",
				zap.Int("port", port),
			)
			return true, fmt.Sprintf("Attempted egress on ISP-restricted port %d", port)
		}
	}

	g.isThrottling = false
	return false, "traffic within safe ISP profile"
}

// IsThrottling returns whether the guard is currently throttling outbound guest networking.
func (g *ISPGuard) IsThrottling() bool {
	g.mu.Lock()
	defer g.mu.Unlock()
	return g.isThrottling
}

// GetViolationCount returns total abuse violations recorded.
func (g *ISPGuard) GetViolationCount() uint32 {
	g.mu.Lock()
	defer g.mu.Unlock()
	return g.violationCounter
}
