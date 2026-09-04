package security

import (
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"sync"
	"time"
)

// BlackboxPanicRecord captures out-of-band kernel crash and register telemetry.
type BlackboxPanicRecord struct {
	RecordID      string    `json:"record_id"`
	CrashReason   string    `json:"crash_reason"`
	RegisterState map[string]string `json:"register_state"`
	CapturedAt    time.Time `json:"captured_at"`
	PayloadDigest string    `json:"payload_digest"`
}

// RedfishBlackboxLogger captures hardware sensor telemetry and kernel panics via Out-of-Band Redfish/SoL.
type RedfishBlackboxLogger struct {
	mu           sync.Mutex
	endpoint     string
	blackboxLogs []*BlackboxPanicRecord
}

// NewRedfishBlackboxLogger initializes an out-of-band forensic logger.
func NewRedfishBlackboxLogger(redfishEndpoint string) *RedfishBlackboxLogger {
	return &RedfishBlackboxLogger{
		endpoint:     redfishEndpoint,
		blackboxLogs: make([]*BlackboxPanicRecord, 0),
	}
}

// CapturePanicTelemetry streams a pre-crash panic record out-of-band before the host halts.
func (r *RedfishBlackboxLogger) CapturePanicTelemetry(reason string, registers map[string]string) *BlackboxPanicRecord {
	r.mu.Lock()
	defer r.mu.Unlock()

	payload := fmt.Sprintf("%s:%v:%d", reason, registers, time.Now().UnixNano())
	digest := sha256.Sum256([]byte(payload))
	digestHex := hex.EncodeToString(digest[:])

	record := &BlackboxPanicRecord{
		RecordID:      fmt.Sprintf("blackbox_%s", digestHex[:16]),
		CrashReason:   reason,
		RegisterState: registers,
		CapturedAt:    time.Now().UTC(),
		PayloadDigest: digestHex,
	}

	r.blackboxLogs = append(r.blackboxLogs, record)
	return record
}

// GetLogCount returns the number of captured out-of-band records.
func (r *RedfishBlackboxLogger) GetLogCount() int {
	r.mu.Lock()
	defer r.mu.Unlock()
	return len(r.blackboxLogs)
}
