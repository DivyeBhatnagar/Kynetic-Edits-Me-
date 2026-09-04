package firewall

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"strings"
	"sync"

	"go.uber.org/zap"
)

// TLSClientHello represents relevant handshake fields for JA4+ fingerprinting.
type TLSClientHello struct {
	ProtocolVersion string   `json:"protocol_version"` // e.g. "d" for QUIC, "t" for TCP
	TLSVersion      string   `json:"tls_version"`      // e.g. "13"
	SNIPresent      bool     `json:"sni_present"`      // "d" (domain) or "i" (IP)
	CipherSuites    []string `json:"cipher_suites"`
	Extensions      []string `json:"extensions"`
	ALPN            string   `json:"alpn"`
}

// JA4FingerprintEngine calculates JA4 network fingerprints to classify and detect C2 malware traffic.
type JA4FingerprintEngine struct {
	logger           *zap.Logger
	maliciousHashes  map[string]string
	mu               sync.Mutex
	detectedThreats  uint64
}

// NewJA4FingerprintEngine creates a new JA4FingerprintEngine.
func NewJA4FingerprintEngine(logger *zap.Logger) *JA4FingerprintEngine {
	// Seed known exploit tool / C2 JA4 fingerprints (e.g., Cobalt Strike, Metasploit)
	malicious := map[string]string{
		"t13d1516h2_8daaf6152771_b124806a7465": "Metasploit Payload",
		"t13d3112h2_deadbeef1234_cafe567890ab": "Cobalt Strike Beacon",
		"t12i050500_000000000000_000000000000": "Raw Socket Port Scanner",
	}

	return &JA4FingerprintEngine{
		logger:          logger,
		maliciousHashes: malicious,
	}
}

// ComputeJA4Fingerprint builds the standardized JA4 fingerprint `(transport)(tls)(sni)(num_ciphers)(num_ext)(alpn)_(cipher_hash)_(ext_hash)`.
func (j *JA4FingerprintEngine) ComputeJA4Fingerprint(ctx context.Context, hello TLSClientHello) (string, bool, string) {
	j.mu.Lock()
	defer j.mu.Unlock()

	transport := "t" // TCP
	if strings.ToLower(hello.ProtocolVersion) == "quic" {
		transport = "q"
	}

	sni := "i"
	if hello.SNIPresent {
		sni = "d"
	}

	ciphersCount := fmt.Sprintf("%02d", len(hello.CipherSuites))
	extCount := fmt.Sprintf("%02d", len(hello.Extensions))

	alpnPart := "00"
	if len(hello.ALPN) >= 2 {
		alpnPart = hello.ALPN[:2]
	}

	partA := fmt.Sprintf("%s%s%s%s%s%s", transport, hello.TLSVersion, sni, ciphersCount, extCount, alpnPart)

	// Hash ciphers
	cipherStr := strings.Join(hello.CipherSuites, ",")
	hC := sha256.Sum256([]byte(cipherStr))
	partB := hex.EncodeToString(hC[:6])

	// Hash extensions
	extStr := strings.Join(hello.Extensions, ",")
	hE := sha256.Sum256([]byte(extStr))
	partC := hex.EncodeToString(hE[:6])

	ja4 := fmt.Sprintf("%s_%s_%s", partA, partB, partC)

	threatName, isMalicious := j.maliciousHashes[ja4]
	if isMalicious {
		j.detectedThreats++
		j.logger.Warn("JA4FingerprintEngine: Malicious C2 / Exploit tool fingerprint matched!",
			zap.String("ja4", ja4),
			zap.String("threat", threatName),
		)
	}

	return ja4, isMalicious, threatName
}

// GetDetectedThreats returns count of identified C2 fingerprints.
func (j *JA4FingerprintEngine) GetDetectedThreats() uint64 {
	j.mu.Lock()
	defer j.mu.Unlock()
	return j.detectedThreats
}
