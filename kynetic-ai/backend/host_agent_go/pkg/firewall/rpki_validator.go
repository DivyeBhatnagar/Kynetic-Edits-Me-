package firewall

import (
	"context"
	"fmt"
	"net"
	"sync"

	"go.uber.org/zap"
)

// RPKIValidationStatus represents BGP route origin authorization result.
type RPKIValidationStatus struct {
	Prefix     string `json:"prefix"`
	ASN        uint32 `json:"asn"`
	Validity   string `json:"validity"` // "valid", "invalid", "not_found"
	IsRejected bool   `json:"is_rejected"`
}

// RPKIValidator performs Route Origin Validation (ROV) on upstream BGP routes and gateways
// to prevent BGP hijacking and traffic interception attacks targeting host compute connections.
type RPKIValidator struct {
	logger        *zap.Logger
	trustedPrefix map[string]uint32
	mu            sync.Mutex
	hijackAlerts  uint64
}

// NewRPKIValidator creates a new RPKIValidator.
func NewRPKIValidator(logger *zap.Logger) *RPKIValidator {
	// Seed known trusted prefix -> ASN mappings
	trusted := map[string]uint32{
		"1.1.1.0/24":    13335, // Cloudflare
		"8.8.8.0/24":    15169, // Google
		"198.51.100.0/24": 64512, // Kynetic Private Transit
	}
	return &RPKIValidator{
		logger:        logger,
		trustedPrefix: trusted,
	}
}

// ValidateRouteOrigin validates an announced IP prefix and origin ASN.
func (r *RPKIValidator) ValidateRouteOrigin(ctx context.Context, prefixCIDR string, originASN uint32) RPKIValidationStatus {
	r.mu.Lock()
	defer r.mu.Unlock()

	_, _, err := net.ParseCIDR(prefixCIDR)
	if err != nil {
		return RPKIValidationStatus{
			Prefix:     prefixCIDR,
			ASN:        originASN,
			Validity:   "invalid_format",
			IsRejected: true,
		}
	}

	expectedASN, exists := r.trustedPrefix[prefixCIDR]
	if !exists {
		// Not in explicit cache, mark as not_found (standard RPKI behavior)
		return RPKIValidationStatus{
			Prefix:     prefixCIDR,
			ASN:        originASN,
			Validity:   "not_found",
			IsRejected: false,
		}
	}

	if expectedASN != originASN {
		r.hijackAlerts++
		r.logger.Warn("RPKIValidator: Potential BGP Hijacking detected! ASN origin mismatch",
			zap.String("prefix", prefixCIDR),
			zap.Uint32("announced_asn", originASN),
			zap.Uint32("expected_asn", expectedASN),
		)
		return RPKIValidationStatus{
			Prefix:     prefixCIDR,
			ASN:        originASN,
			Validity:   "invalid",
			IsRejected: true,
		}
	}

	return RPKIValidationStatus{
		Prefix:     prefixCIDR,
		ASN:        originASN,
		Validity:   "valid",
		IsRejected: false,
	}
}

// GetHijackAlertsCount returns count of identified BGP route hijacking anomalies.
func (r *RPKIValidator) GetHijackAlertsCount() uint64 {
	r.mu.Lock()
	defer r.mu.Unlock()
	return r.hijackAlerts
}

// RegisterTrustedPrefix registers an additional ROA prefix to ASN binding.
func (r *RPKIValidator) RegisterTrustedPrefix(prefix string, asn uint32) error {
	r.mu.Lock()
	defer r.mu.Unlock()
	if _, _, err := net.ParseCIDR(prefix); err != nil {
		return fmt.Errorf("invalid CIDR: %w", err)
	}
	r.trustedPrefix[prefix] = asn
	return nil
}
