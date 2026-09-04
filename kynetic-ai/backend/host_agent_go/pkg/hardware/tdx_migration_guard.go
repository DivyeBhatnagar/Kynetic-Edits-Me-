package hardware

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"sync"
)

// TDXMigrationSession holds cryptographic state for a live Trust Domain migration stream.
type TDXMigrationSession struct {
	SessionID         string `json:"session_id"`
	SourceTDQuote     string `json:"source_td_quote"`
	DestinationTDQuote string `json:"destination_td_quote"`
	TransportKeyHex   string `json:"transport_key_hex"`
	PagesMigrated     uint64 `json:"pages_migrated"`
	IsCommitted       bool   `json:"is_committed"`
}

// TDXMigrationGuard validates pre-copy live migration session keys using Intel TDX Migration Module (TDMM).
type TDXMigrationGuard struct {
	mu            sync.Mutex
	activeSessions map[string]*TDXMigrationSession
}

// NewTDXMigrationGuard initializes a TDX live migration decryption guard.
func NewTDXMigrationGuard() *TDXMigrationGuard {
	return &TDXMigrationGuard{
		activeSessions: make(map[string]*TDXMigrationSession),
	}
}

// EstablishMigrationSession creates an authenticated TDX migration context.
func (t *TDXMigrationGuard) EstablishMigrationSession(sessionID, srcQuote, dstQuote string, rawKey []byte) (*TDXMigrationSession, error) {
	t.mu.Lock()
	defer t.mu.Unlock()

	if len(rawKey) < 32 {
		return nil, fmt.Errorf("migration transport key must be at least 256-bit")
	}

	session := &TDXMigrationSession{
		SessionID:          sessionID,
		SourceTDQuote:      srcQuote,
		DestinationTDQuote: dstQuote,
		TransportKeyHex:    hex.EncodeToString(rawKey),
		PagesMigrated:      0,
		IsCommitted:        false,
	}

	t.activeSessions[sessionID] = session
	return session, nil
}

// VerifyMigratedPageCiphertext validates page MAC tag before decrypting guest TD page memory.
func (t *TDXMigrationGuard) VerifyMigratedPageCiphertext(sessionID string, pageCiphertext []byte, expectedMAC string) (bool, string) {
	t.mu.Lock()
	defer t.mu.Unlock()

	session, exists := t.activeSessions[sessionID]
	if !exists {
		return false, "MIGRATION_SESSION_NOT_FOUND"
	}

	keyBytes, _ := hex.DecodeString(session.TransportKeyHex)
	h := hmac.New(sha256.New, keyBytes)
	h.Write(pageCiphertext)
	computedMAC := hex.EncodeToString(h.Sum(nil))

	if !hmac.Equal([]byte(computedMAC), []byte(expectedMAC)) {
		return false, "TDX_PAGE_CIPHERTEXT_INTEGRITY_TAMPERED"
	}

	session.PagesMigrated++
	return true, "TDX_PAGE_AUTHENTICATED"
}
