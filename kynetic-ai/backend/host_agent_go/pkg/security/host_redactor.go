package security

import (
	"crypto/sha256"
	"encoding/hex"
	"regexp"
	"strings"
	"sync"

	"go.uber.org/zap"
)

// HostInfoRedactor masks sensitive host identification data (MAC addresses, motherboard UUIDs,
// serial numbers) exposed in system logs or guest queries to prevent host doxxing and tracking.
type HostInfoRedactor struct {
	logger        *zap.Logger
	macRegex      *regexp.Regexp
	uuidRegex     *regexp.Regexp
	mu            sync.Mutex
	redactedCount uint64
}

// NewHostInfoRedactor creates a new HostInfoRedactor.
func NewHostInfoRedactor(logger *zap.Logger) *HostInfoRedactor {
	return &HostInfoRedactor{
		logger:    logger,
		macRegex:  regexp.MustCompile(`(?i)([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})`),
		uuidRegex: regexp.MustCompile(`(?i)[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}`),
	}
}

// RedactString replaces MAC addresses and UUIDs with pseudonymized SHA-256 hashes.
func (h *HostInfoRedactor) RedactString(raw string) string {
	h.mu.Lock()
	defer h.mu.Unlock()

	result := h.macRegex.ReplaceAllStringFunc(raw, func(mac string) string {
		h.redactedCount++
		digest := sha256.Sum256([]byte(mac))
		return "MAC:REDACTED:" + hex.EncodeToString(digest[:3])
	})

	result = h.uuidRegex.ReplaceAllStringFunc(result, func(uuid string) string {
		h.redactedCount++
		digest := sha256.Sum256([]byte(uuid))
		return "UUID:REDACTED:" + hex.EncodeToString(digest[:4])
	})

	// Redact standard serial keywords
	result = strings.ReplaceAll(result, "System Serial Number", "System Serial: REDACTED")

	return result
}

// GetRedactedCount returns count of redacted identifiers.
func (h *HostInfoRedactor) GetRedactedCount() uint64 {
	h.mu.Lock()
	defer h.mu.Unlock()
	return h.redactedCount
}
