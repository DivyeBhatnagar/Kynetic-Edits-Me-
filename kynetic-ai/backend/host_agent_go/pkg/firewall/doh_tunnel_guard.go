package firewall

import (
	"context"
	"math"
	"strings"
	"sync"

	"go.uber.org/zap"
)

// DNSTunnelingScore represents statistical analysis of a domain query.
type DNSTunnelingScore struct {
	QueryDomain      string  `json:"query_domain"`
	ShannonEntropy   float64 `json:"shannon_entropy"`
	IsTunnelingSuspect bool  `json:"is_tunneling_suspect"`
	SubdomainDepth   int     `json:"subdomain_depth"`
}

// DOHTunnelGuard inspects DNS queries from guest environments and detects
// high-entropy encoded DNS tunneling attacks used for C2 beaconing or data exfiltration.
type DOHTunnelGuard struct {
	logger           *zap.Logger
	entropyThreshold float64
	mu               sync.Mutex
	blockedQueries   uint64
}

// NewDOHTunnelGuard creates a new DOHTunnelGuard.
func NewDOHTunnelGuard(logger *zap.Logger, entropyThreshold float64) *DOHTunnelGuard {
	if entropyThreshold <= 0 {
		entropyThreshold = 3.8 // Shannon entropy > 3.8 indicates high-entropy base64/hex payload
	}
	return &DOHTunnelGuard{
		logger:           logger,
		entropyThreshold: entropyThreshold,
	}
}

// CalculateEntropy computes Shannon entropy of a string.
func (d *DOHTunnelGuard) CalculateEntropy(s string) float64 {
	if len(s) == 0 {
		return 0
	}
	freq := make(map[rune]float64)
	for _, r := range s {
		freq[r]++
	}
	var entropy float64
	length := float64(len(s))
	for _, count := range freq {
		p := count / length
		entropy -= p * math.Log2(p)
	}
	return entropy
}

// EvaluateDomainQuery checks if a domain query shows statistical characteristics of DNS tunneling.
func (d *DOHTunnelGuard) EvaluateDomainQuery(ctx context.Context, domain string) DNSTunnelingScore {
	d.mu.Lock()
	defer d.mu.Unlock()

	parts := strings.Split(domain, ".")
	subdomainDepth := len(parts)

	longestLabel := ""
	for _, p := range parts {
		if len(p) > len(longestLabel) {
			longestLabel = p
		}
	}

	entropy := d.CalculateEntropy(longestLabel)
	isSuspect := false

	// If single label is >25 chars with high entropy or subdomain depth > 4
	if (len(longestLabel) > 25 && entropy > d.entropyThreshold) || (subdomainDepth > 5 && entropy > 3.5) {
		isSuspect = true
		d.blockedQueries++
		d.logger.Warn("DOHTunnelGuard: High-entropy DNS tunneling query detected & flagged",
			zap.String("domain", domain),
			zap.Float64("entropy", entropy),
		)
	}

	return DNSTunnelingScore{
		QueryDomain:        domain,
		ShannonEntropy:     entropy,
		IsTunnelingSuspect: isSuspect,
		SubdomainDepth:     subdomainDepth,
	}
}

// GetBlockedCount returns count of flagged DNS tunneling queries.
func (d *DOHTunnelGuard) GetBlockedCount() uint64 {
	d.mu.Lock()
	defer d.mu.Unlock()
	return d.blockedQueries
}
